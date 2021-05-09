# CIDRPit - Lightweight Serverless API based IPAM

Built with AWS Lambda and DynamoDB.

## Terminology

A *pool* is a name that can contain multiple *roots*. E.g. "dev", "prod". Pools don't have to be explicitly created.

A *root* is a CIDR that is available for consumption. E.g. 10.0.0.0/16.

A *reservation* is a CIDR that has been reserved.

## Setup

(Currently only for local dev)

```
pip install -r requirements.txt
python setup.py
```

## Running the API

```
flask run 
```

This is supposed to also run in Lambda using serverless-wsgi once the IaC is ready. See handler.py.

## Requests

List roots and reservations, optionally by pool:

```
curl http://localhost:5000/roots/
curl http://localhost:5000/roots/dev
curl http://localhost:5000/reservations/
curl http://localhost:5000/reservations/dev
```

Create a root:

```
curl -X POST http://localhost:5000/roots/dev -H 'Content-type: application/json' -d '{"cidr":"10.0.0.0/16"}'
```

Create a reservation by prefix length:

```
curl -X POST http://localhost:5000/reservations/dev -H 'Content-type: application/json' -d '{"prefix_length":28,"comment":"My nice reservation"}'
```

Create a reservation by CIDR:

```
curl -X POST http://localhost:5000/reservations/dev -H 'Content-type: application/json' -d '{"cidr":"10.0.24.0/24","comment":"My specific reservation"}'
```

Delete a reservation:

```
curl -X DELETE http://localhost:5000/reservations/dev/10.0.24.0/24 
```

Delete a root (must be empty):

```
curl -X DELETE http://localhost:5000/root/dev/10.0.0.0/16 
```

## Using the python interface

```python
import main

main.create_root('10.0.0.0/16', 'dev')
main.create_root('10.2.0.0/16', 'prod')

main.allocate(24, 'dev')
main.allocate_by_cidr('dev', '10.0.112.0/24')

for root in main.list_roots():
    print(f'{root.cidr} {root.pool_name}')

main.deallocate('10.0.112.0/24')
main.delete_root('10.0.0.0/16')
```