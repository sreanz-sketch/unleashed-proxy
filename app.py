import os
import hmac
import hashlib
import base64
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)

CORS(app, resources={r"/*": {
    "origins": "*",
    "methods": ["GET", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"]
}})

API_ID = os.environ.get('UNLEASHED_API_ID')
API_KEY = os.environ.get('UNLEASHED_API_KEY')
CLIENT_TYPE = os.environ.get('UNLEASHED_CLIENT_TYPE', 'marathonproductslimited/api')
BASE_URL = 'https://api.unleashedsoftware.com'


def get_signature(query_string, api_key):
    key_bytes = api_key.encode('utf-8')
    msg_bytes = query_string.encode('utf-8')
    sig = hmac.new(key_bytes, msg_bytes, hashlib.sha256).digest()
    return base64.b64encode(sig).decode('utf-8')


def unleashed_get(endpoint, query_string=''):
    sig = get_signature(query_string, API_KEY)
    url = f'{BASE_URL}/{endpoint}'
    if query_string:
        url += f'?{query_string}'
    headers = {
        'api-auth-id': API_ID,
        'api-auth-signature': sig,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'client-type': CLIENT_TYPE,
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    # Guard against non-JSON responses
    content_type = resp.headers.get('Content-Type', '')
    if 'application/json' not in content_type and 'text/json' not in content_type:
        raise ValueError(f'Non-JSON response from Unleashed: {resp.status_code} {resp.text[:200]}')
    return resp.json()


@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'api_id_set': bool(API_ID), 'api_key_set': bool(API_KEY)})


@app.route('/stock-on-hand')
def stock_on_hand():
    try:
        all_items = []
        page = 1
        while page <= 20:
            qs = 'pageSize=200'
            data = unleashed_get(f'StockOnHand/{page}', qs)
            items = data.get('Items', [])
            all_items.extend(items)
            pagination = data.get('Pagination', {})
            total_pages = pagination.get('NumberOfPages', 1)
            if page >= total_pages or len(items) < 200:
                break
            page += 1
        return jsonify({'success': True, 'total': len(all_items), 'items': all_items})
    except requests.HTTPError as e:
        body = e.response.text if e.response else ''
        return jsonify({'success': False, 'error': f'Unleashed {e.response.status_code}: {body}'}), 502
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/sales-orders')
def sales_orders():
    """Fetch sales orders, filtering client-side by orderNumber."""
    try:
        raw = request.args.get('orderNumber', '').strip()
        # Normalise: extract digits and zero-pad to SO-XXXXXXXX
        digits = ''.join(filter(str.isdigit, raw))
        order_number = f'SO-{digits.zfill(8)}' if digits else ''

        all_items = []
        page = 1
        while page <= 20:
            qs = 'pageSize=200'
            try:
                data = unleashed_get(f'SalesOrders/{page}', qs)
            except (ValueError, requests.HTTPError) as page_err:
                # Log and stop pagination on bad page
                break
            items = data.get('Items', [])
            if not items:
                break
            # Filter client-side if order number provided
            if order_number:
                match = next((o for o in items if str(o.get('OrderNumber', '')) == order_number), None)
                if match:
                    return jsonify({'success': True, 'total': 1, 'items': [match]})
            else:
                all_items.extend(items)
            pagination = data.get('Pagination', {})
            total_pages = pagination.get('NumberOfPages', 1)
            if page >= total_pages or len(items) < 200:
                break
            page += 1

        if order_number and not all_items:
            return jsonify({'success': True, 'total': 0, 'items': [], 'note': f'{order_number} not found'})

        return jsonify({'success': True, 'total': len(all_items), 'items': all_items})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/purchase-orders')
def purchase_orders():
    """Fetch purchase orders, filtering client-side by orderNumber."""
    try:
        raw = request.args.get('orderNumber', '').strip()
        digits = ''.join(filter(str.isdigit, raw))
        order_number = f'PO-{digits.zfill(8)}' if digits else ''

        all_items = []
        page = 1
        while page <= 20:
            qs = 'pageSize=200'
            try:
                data = unleashed_get(f'PurchaseOrders/{page}', qs)
            except (ValueError, requests.HTTPError):
                break
            items = data.get('Items', [])
            if not items:
                break
            if order_number:
                match = next((o for o in items if str(o.get('OrderNumber', '')) == order_number), None)
                if match:
                    return jsonify({'success': True, 'total': 1, 'items': [match]})
            else:
                all_items.extend(items)
            pagination = data.get('Pagination', {})
            total_pages = pagination.get('NumberOfPages', 1)
            if page >= total_pages or len(items) < 200:
                break
            page += 1

        return jsonify({'success': True, 'total': len(all_items), 'items': all_items})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/products')
def products():
    try:
        all_items = []
        page = 1
        while page <= 20:
            qs = 'pageSize=200'
            data = unleashed_get(f'Products/{page}', qs)
            items = data.get('Items', [])
            all_items.extend(items)
            pagination = data.get('Pagination', {})
            total_pages = pagination.get('NumberOfPages', 1)
            if page >= total_pages or len(items) < 200:
                break
            page += 1
        return jsonify({'success': True, 'total': len(all_items), 'items': all_items})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
