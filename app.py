from flask import Flask, redirect, jsonify, request

import main

app = Flask('CIDRPit', static_url_path='/ui', static_folder='static')


@app.route("/ui/")
def redirect_to_ui():
    return redirect('/ui/index.html', 301)


@app.route("/roots/")
@app.route("/roots/<pool>")
def get_roots(pool = None):
    roots = main.list_roots(pool)
    return jsonify([{'cidr': root.cidr, 'pool_name': root.pool_name} for root in roots])


@app.route("/roots/<pool>", methods=['POST'])
def create_root(pool: str):
    cidr = request.json.get('cidr', None)
    if not cidr:
        return jsonify({'msg': 'Please provide cidr in body'}), 400
    try:
        main.create_root(cidr, pool)
    except Exception as e:
        return jsonify({'msg': str(e)}), 400
    return jsonify({'msg': 'ok'}), 200


# TODO: we're ignoring the pool for now. maybe rework the entire URL concept?
@app.route("/roots/<pool>/<path:cidr>", methods=['DELETE'])
def delete_root(pool: str, cidr: str):
    try:
        main.delete_root(cidr)
    except Exception as e:
        return jsonify({'msg': str(e)}), 400
    return jsonify({'msg': 'ok'}), 200


# TODO: figure out how to do reservations by root with clean URLs.
@app.route("/reservations/")
@app.route("/reservations/<pool>")
def get_reservations(pool = None):
    reservations = main.list_reservations_by_pool(pool)
    return jsonify([{'cidr': reservation.cidr, 'pool_name': reservation.reservation_in_pool, 'created': reservation.created, 'comment': reservation.comment} for reservation in reservations])


@app.route("/reservations/<pool>", methods=['POST'])
def create_reservations(pool):
    comment = request.json.get('comment', '')
    try:
        cidr = request.json.get('cidr')
        if cidr:
            reservation = main.allocate_by_cidr(pool, cidr, comment)
        else:
            prefix_length = request.json.get('prefix_length')
            if not prefix_length:
                raise Exception('Please provide prefix_length in body or cidr in path.')
            reservation = main.allocate(prefix_length, pool, comment)

    except Exception as e:
        return jsonify({'msg': str(e)}), 400

    return jsonify({'cidr': reservation.cidr, 'pool_name': reservation.reservation_in_pool, 'created': reservation.created, 'comment': reservation.comment})


@app.route("/reservations/<pool>/<path:cidr>", methods=['DELETE'])
def delete_reservation(pool: str, cidr: str):
    try:
        main.deallocate(cidr)
    except Exception as e:
        return jsonify({'msg': str(e)}), 400
    return jsonify({'msg': 'ok'}), 200