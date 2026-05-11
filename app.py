import os
import hmac
import hashlib
import base64
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Allow requests from Claude.ai

API_ID = os.environ.get('UNLEASHED_API_ID')
API_KEY = os.environ.get('UNLEASHED_API_KEY')
CLIENT_TYPE = os.environ.get('UNLEASHED_CLIENT_TYPE', 'marathonproductslimited/api')
BASE_URL = 'https://api.unleashedsoftware.com'


def get_signature(query_string, api_key):
    """Generate HMAC-SHA256 signature from query string."""
    key_bytes = api_key.encode('utf-8')
    msg_bytes = query_string.encode('utf-8')
    sig = hmac.new(key_bytes, msg_bytes, hashlib.sha256).digest()
    return base64.b64encode(sig).decode('utf-8')


def unleashed_get(endpoint, query_string=''):
    """Make an authenticated GET request to the Unleashed API."""
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
    return resp.json()


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/stock-on-hand')
def stock_on_hand():
    """Fetch all stock on hand, paginating automatically."""
    try:
        all_items = []
        page = 1
        while page <= 20:
            qs = f'pageSize=200'
            data = unleashed_get(f'StockOnHand/{page}', qs)
            items = data.get('Items', [])
            all_items.extend(items)
            pagination = data.get('Pagination', {})
            total_pages = pagination.get('NumberOfPages', 1)
            if page >= total_pages or len(items) < 200:
                break
            page += 1

        return jsonify({
            'success': True,
            'total': len(all_items),
            'items': all_items
        })
    except requests.HTTPError as e:
        return jsonify({'success': False, 'error': f'Unleashed API error: {e.response.status_code}'}), 502
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/stock-on-hand/<product_guid>')
def stock_on_hand_product(product_guid):
    """Fetch stock on hand for a specific product."""
    try:
        data = unleashed_get(f'StockOnHand/{product_guid}')
        return jsonify({'success': True, 'item': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/products')
def products():
    """Fetch all products."""
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
