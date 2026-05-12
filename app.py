import os
import hmac
import hashlib
import base64
import requests
from datetime import datetime
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
    return resp


def parse_date(date_val):
    """Parse Unleashed /Date(ms)/ or ISO string to datetime."""
    if not date_val:
        return None
    s = str(date_val)
    import re
    m = re.search(r'\d+', s)
    if m:
        return datetime.utcfromtimestamp(int(m.group()) / 1000)
    try:
        return datetime.fromisoformat(s[:10])
    except Exception:
        return None


def fetch_all_pages(endpoint):
    """Fetch all pages from an Unleashed endpoint, return list of items."""
    all_items = []
    page = 1
    while page <= 50:
        qs = 'pageSize=200'
        resp = unleashed_get(f'{endpoint}/{page}', qs)
        if resp.status_code != 200:
            raise Exception(f'Unleashed {resp.status_code}: {resp.text[:300]}')
        data = resp.json()
        items = data.get('Items', [])
        if not items:
            break
        all_items.extend(items)
        pagination = data.get('Pagination', {})
        total_pages = pagination.get('NumberOfPages', 1)
        if page >= total_pages or len(items) < 200:
            break
        page += 1
    return all_items


@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'api_id_set': bool(API_ID), 'api_key_set': bool(API_KEY)})


@app.route('/debug')
def debug():
    try:
        qs = 'pageSize=5'
        resp = unleashed_get('SalesOrders/1', qs)
        return jsonify({
            'status_code': resp.status_code,
            'content_type': resp.headers.get('Content-Type', ''),
            'body_preview': resp.text[:500],
            'success': resp.status_code == 200
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/stock-on-hand')
def stock_on_hand():
    try:
        all_items = fetch_all_pages('StockOnHand')
        return jsonify({'success': True, 'total': len(all_items), 'items': all_items})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/sales-orders')
def sales_orders():
    try:
        raw = request.args.get('orderNumber', '').strip()
        digits = ''.join(filter(str.isdigit, raw))
        order_number = f'SO-{digits.zfill(8)}' if digits else ''

        all_items = fetch_all_pages('SalesOrders')

        if order_number:
            match = next((o for o in all_items if str(o.get('OrderNumber', '')) == order_number), None)
            if match:
                return jsonify({'success': True, 'total': 1, 'items': [match]})
            return jsonify({'success': True, 'total': 0, 'items': [], 'note': f'{order_number} not found'})

        return jsonify({'success': True, 'total': len(all_items), 'items': all_items})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/revenue-summary')
def revenue_summary():
    """
    Return completed sales orders filtered by date range.
    Query params:
      startDate: YYYY-MM-DD (default: first day of current month)
      endDate:   YYYY-MM-DD (default: today)
    """
    try:
        today = datetime.utcnow()
        default_start = today.replace(day=1).strftime('%Y-%m-%d')
        default_end = today.strftime('%Y-%m-%d')

        start_str = request.args.get('startDate', default_start)
        end_str = request.args.get('endDate', default_end)

        start_dt = datetime.strptime(start_str, '%Y-%m-%d')
        end_dt = datetime.strptime(end_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)

        all_orders = fetch_all_pages('SalesOrders')

        # Filter to completed orders within date range (using CompletedDate)
        filtered = []
        for o in all_orders:
            if o.get('OrderStatus') != 'Completed':
                continue
            completed = parse_date(o.get('CompletedDate'))
            if completed and start_dt <= completed <= end_dt:
                filtered.append(o)

        # Aggregate
        total_revenue = sum(o.get('BCSubTotal', 0) for o in filtered)
        total_tax = sum(o.get('BCTaxTotal', 0) for o in filtered)
        total_inc_tax = sum(o.get('BCTotal', 0) for o in filtered)
        order_count = len(filtered)

        # Per customer breakdown
        customers = {}
        for o in filtered:
            name = o.get('Customer', {}).get('CustomerName', 'Unknown')
            if name not in customers:
                customers[name] = {'order_count': 0, 'subtotal': 0, 'total': 0, 'orders': []}
            customers[name]['order_count'] += 1
            customers[name]['subtotal'] += o.get('BCSubTotal', 0)
            customers[name]['total'] += o.get('BCTotal', 0)
            customers[name]['orders'].append(o.get('OrderNumber'))

        # Per salesperson breakdown
        salespeople = {}
        for o in filtered:
            sp = o.get('SalesPerson')
            name = sp.get('FullName', 'Unknown') if sp else 'Unassigned'
            if name not in salespeople:
                salespeople[name] = {'order_count': 0, 'total': 0}
            salespeople[name]['order_count'] += 1
            salespeople[name]['total'] += o.get('BCTotal', 0)

        # Top products by qty sold
        products = {}
        for o in filtered:
            for line in o.get('SalesOrderLines', []):
                product = line.get('Product', {})
                code = product.get('ProductCode', 'Unknown')
                desc = product.get('ProductDescription', '')
                qty = line.get('OrderQuantity', 0)
                revenue = line.get('BCLineTotal', 0)
                if code not in products:
                    products[code] = {'description': desc, 'qty': 0, 'revenue': 0}
                products[code]['qty'] += qty
                products[code]['revenue'] += revenue

        return jsonify({
            'success': True,
            'period': {'start': start_str, 'end': end_str},
            'summary': {
                'order_count': order_count,
                'subtotal_excl_tax': round(total_revenue, 2),
                'tax': round(total_tax, 2),
                'total_incl_tax': round(total_inc_tax, 2),
            },
            'by_customer': sorted(
                [{'customer': k, **v} for k, v in customers.items()],
                key=lambda x: x['total'], reverse=True
            ),
            'by_salesperson': sorted(
                [{'salesperson': k, **v} for k, v in salespeople.items()],
                key=lambda x: x['total'], reverse=True
            ),
            'top_products': sorted(
                [{'code': k, **v} for k, v in products.items()],
                key=lambda x: x['qty'], reverse=True
            )[:20],
            'orders': [
                {
                    'order_number': o.get('OrderNumber'),
                    'customer': o.get('Customer', {}).get('CustomerName'),
                    'completed_date': parse_date(o.get('CompletedDate')).strftime('%Y-%m-%d') if parse_date(o.get('CompletedDate')) else None,
                    'salesperson': o.get('SalesPerson', {}).get('FullName') if o.get('SalesPerson') else None,
                    'subtotal': o.get('BCSubTotal', 0),
                    'tax': o.get('BCTaxTotal', 0),
                    'total': o.get('BCTotal', 0),
                    'delivery_method': o.get('DeliveryMethod'),
                    'customer_ref': o.get('CustomerRef'),
                    'order_group': o.get('SalesOrderGroup'),
                }
                for o in sorted(filtered, key=lambda x: parse_date(x.get('CompletedDate')) or datetime.min, reverse=True)
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/purchase-orders')
def purchase_orders():
    try:
        raw = request.args.get('orderNumber', '').strip()
        digits = ''.join(filter(str.isdigit, raw))
        order_number = f'PO-{digits.zfill(8)}' if digits else ''

        all_items = fetch_all_pages('PurchaseOrders')

        if order_number:
            match = next((o for o in all_items if str(o.get('OrderNumber', '')) == order_number), None)
            if match:
                return jsonify({'success': True, 'total': 1, 'items': [match]})
            return jsonify({'success': True, 'total': 0, 'items': [], 'note': f'{order_number} not found'})

        return jsonify({'success': True, 'total': len(all_items), 'items': all_items})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/products')
def products():
    try:
        all_items = fetch_all_pages('Products')
        return jsonify({'success': True, 'total': len(all_items), 'items': all_items})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
