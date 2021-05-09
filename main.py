from ipaddress import IPv4Network
import time
import logging

from pynamodb.transactions import TransactWrite, TransactGet
from pynamodb.connection import Connection
from pynamodb.exceptions import DoesNotExist
from model import CidrPitModel

# logging.basicConfig(level='INFO')

connection = Connection()

# From being the supernet, to being the subnet
def _get_rootline(from_cidr: str, to_cidr: str) -> list:
    from_net = IPv4Network(from_cidr)
    to_net = IPv4Network(to_cidr)
    futures = []
    with TransactGet(connection=connection) as transaction:
        current = to_net
        while current.prefixlen >= from_net.prefixlen:
            futures.append(transaction.get(CidrPitModel, str(current), current.prefixlen))
            current = current.supernet()
    return futures

def _create_reservation(top: CidrPitModel, to_net: IPv4Network, comment: str):
    from_net = top.net
    rootline = []
    current = to_net
    while current.prefixlen >= from_net.prefixlen:
        rootline.append(current)
        current = current.supernet()
    rootline.reverse()

    logging.info(f'creating reservation for {rootline}')

    index = 0
    with TransactWrite(connection=connection) as transaction:
        for net in rootline:
            if index == 0:
                is_left = _is_left(rootline[index+1])
                if top.root_of_pool:
                    # we never delete roots
                    if top.left_free == 'Y' and is_left == True:
                        if top.right_free == 'N':
                            logging.info(f'updating root {top.cidr}: Set left to taken, remove from capacity')
                            transaction.update(
                                top,
                                actions=[CidrPitModel.left_free.set('N'), CidrPitModel.capacity_in_pool.remove()],
                                condition=((CidrPitModel.left_free == 'Y') & (CidrPitModel.right_free == 'N'))
                            )
                        else:
                            logging.info(f'updating root {top.cidr}: Set left to taken, right still available')
                            transaction.update(
                                top,
                                actions=[CidrPitModel.left_free.set('N')],
                                condition=((CidrPitModel.left_free == 'Y') & (CidrPitModel.right_free == 'Y'))
                            )
                    elif top.right_free == 'Y' and is_left == False:
                        if top.left_free == 'N':
                            logging.info(f'updating root {top.cidr}: Set right to taken, remove from capacity')
                            transaction.update(
                                top,
                                actions=[CidrPitModel.right_free.set('N'), CidrPitModel.capacity_in_pool.remove()],
                                condition=((CidrPitModel.right_free == 'Y') & (CidrPitModel.left_free == 'N'))
                            )
                        else:
                            logging.info(f'updating root {top.cidr}: Set right to taken, right still available')
                            transaction.update(
                                top,
                                actions=[CidrPitModel.right_free.set('N')],
                                condition=((CidrPitModel.right_free == 'Y') & (CidrPitModel.left_free == 'Y'))
                            )
                    else:
                        raise Exception(f'Error finding free capacity on {str(top.net)}')

                else:
                    # non-root capacity cidrs are always partially taken and need to be removed
                    if top.left_free == 'Y' and is_left == True:
                        transaction.delete(
                            top,
                            condition=((CidrPitModel.left_free == 'Y') & (CidrPitModel.right_free == 'N'))
                        )
                    elif top.right_free == 'Y' and is_left == False:
                        transaction.delete(
                            top,
                            condition=((CidrPitModel.right_free == 'Y') & (CidrPitModel.left_free == 'N'))
                        )
                    else:
                        raise Exception('this should not happen')

            elif index < len(rootline) - 1:
                is_left = _is_left(rootline[index+1])
                record = CidrPitModel(
                    str(net),
                    net.prefixlen,
                    left_free='N' if is_left else 'Y',
                    right_free='Y' if is_left else 'N',
                    pool_name=top.pool_name,
                    root_cidr=top.root_cidr,
                    capacity_in_pool=top.pool_name,
                    created=int(time.time())
                )
                logging.info(f'saving intermediate {record.cidr}')
                transaction.save(record, (CidrPitModel.cidr.does_not_exist()))
            else:
                record = CidrPitModel(
                    str(net),
                    net.prefixlen,
                    left_free='N',
                    right_free='N',
                    pool_name=top.pool_name,
                    root_cidr=top.root_cidr,
                    reservation_in_pool=top.pool_name,
                    comment=comment,
                    created=int(time.time())
                )
                logging.info(f'saving reservation {record.__dict__}')
                transaction.save(record, condition=(CidrPitModel.cidr.does_not_exist()))
                return record

            index += 1


def create_root(cidr: str, pool: str):
    net = IPv4Network(cidr)

    for root in CidrPitModel.root_index.scan():
        root_net = IPv4Network(root.cidr)
        if root_net.subnet_of(net) or net.subnet_of(root_net):
            raise Exception(f'CIDR conflicts with existing root {str(root_net)}')

    record = CidrPitModel(
        str(net),
        net.prefixlen,
        left_free='Y',
        right_free='Y',
        pool_name=pool,
        capacity_in_pool=pool,
        root_of_pool=pool,
        root_cidr=str(net),
        created=int(time.time())
    )

    logging.info(f'saving root {record.cidr}')

    record.save()


def delete_root(cidr: str):
    net = IPv4Network(cidr)
    try:
        root = CidrPitModel.get(str(net), net.prefixlen)
    except:
        root = None

    if not root:
        raise Exception(f'Root {str(net)} does not exist.')

    if root.root_cidr != root.cidr:
        raise Exception(f'{str(net)} is not a root.')

    if root.left_free != 'Y' or root.right_free != 'Y':
        raise Exception(f'{str(net)} is not empty.')

    try:
        root.delete((CidrPitModel.left_free == 'Y') & (CidrPitModel.right_free == 'Y'))
    except:
        raise Exception(f'Unknown error.')


def list_roots(pool: str = None):
    if pool:
        roots = CidrPitModel.root_index.query(pool)
    else:
        roots = CidrPitModel.root_index.scan()

    return list(roots)


def list_reservations_by_pool(pool: str = None):
    if pool:
        reservations = CidrPitModel.reservation_by_pool_index.query(pool)
    else:
        reservations = CidrPitModel.reservation_by_pool_index.scan()

    return list(reservations)


def list_reservations_by_root(root: str):
    return list(CidrPitModel.reservation_by_root_index.query(root))


def allocate(size: int, pool: str, comment: str = ''):
    results = list(CidrPitModel.free_capacity_index.query(pool, CidrPitModel.prefix_length < size, scan_index_forward=False, limit=1))
    if len(results) == 0:
        raise Exception(f'No capacity available in pool {pool}')
    top = results[0]
    if top.left_free == 'Y':
        net = list(top.net.subnets())[0]
    else:
        net = list(top.net.subnets())[1]
    logging.info(f'first intermediate or reservation to create: {net}')
    reservation_net = IPv4Network(f'{net.network_address}/{size}')
    return _create_reservation(top, reservation_net, comment)


def _is_left(net: IPv4Network) -> bool:
    cidr = str(net)
    siblings = [str(sibling) for sibling in net.supernet().subnets()]
    return siblings.index(cidr) == 0

def deallocate(cidr: str):
    net = IPv4Network(cidr)
    try:
        record = CidrPitModel.get(str(net), net.prefixlen)
    except:
        record = None
    if not record or not record.reservation_in_pool:
        raise Exception(f'CIDR {cidr} is not a reservation')

    futures = _get_rootline(record.root_cidr, cidr)

    with TransactWrite(connection=connection) as transaction:
        try:
            reservation = futures.pop(0).get()
        except DoesNotExist:
            raise Exception(f'Reservation {cidr} seems to have disappeared.')

        try:
            root = futures.pop().get()
        except DoesNotExist:
            raise Exception(f'Cannot find root {str(record.root_cidr)}')

        transaction.delete(reservation, condition=CidrPitModel.cidr.exists())

        is_left = _is_left(net)
        parent = net.supernet()
        for future in futures:
            try:
                intermediate = future.get()
                logging.info(f'deleting {intermediate.cidr}')
                transaction.delete(intermediate, condition=CidrPitModel.cidr.exists())
                is_left = _is_left(IPv4Network(intermediate.cidr))
                parent = parent.supernet()
            except DoesNotExist:
                # create intermediate CIDR and stop
                record = CidrPitModel(
                    str(parent),
                    parent.prefixlen,
                    left_free= 'Y' if is_left else 'N',
                    right_free='N' if is_left else 'Y',
                    pool_name=record.pool_name,
                    root_cidr=record.root_cidr,
                    capacity_in_pool=record.pool_name,
                    created=int(time.time())
                )
                logging.info(f'saving {record.__dict__}')
                transaction.save(record, (CidrPitModel.cidr.does_not_exist()))
                return

        # if we have a straight line to the root, we update it.
        if is_left:
            transaction.update(
                root,
                actions=[CidrPitModel.left_free.set('Y'), CidrPitModel.capacity_in_pool.set(root.pool_name)],
                condition=(CidrPitModel.left_free == 'N')
            )
        else:
            transaction.update(
                root,
                actions=[CidrPitModel.right_free.set('Y'), CidrPitModel.capacity_in_pool.set(root.pool_name)],
                condition=(CidrPitModel.right_free == 'N')
            )


def allocate_by_cidr(pool: str, cidr: str, comment: str = ''):
    net = IPv4Network(cidr)
    roots = list_roots(pool)
    for root in roots:
        if net.subnet_of(root.net):
            root_net = root.net
            futures = _get_rootline(root.cidr, cidr)
            current = net
            index = 0
            is_left = _is_left(net)
            while current.prefixlen >= root_net.prefixlen:
                try:
                    current_record = futures[index].get()
                    if index == 0:
                        raise Exception(f'CIDR {cidr} is not available')
                    else:
                        if is_left and current_record.left_free == 'Y' or is_left == False and current_record.right_free == 'Y':
                            return _create_reservation(current_record, net, comment)
                        else:
                            raise Exception(f'CIDR {cidr} cannot be allocated because of a conflict on {current_record.cidr}')
                except DoesNotExist:
                    pass

                index += 1
                is_left = _is_left(current)
                current = current.supernet()

    raise Exception(f'No root for {cidr} in pool {pool}')
