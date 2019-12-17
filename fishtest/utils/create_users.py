import os
import sys

sys.path.append(os.path.expanduser('fishtest'))

from rundb import RunDb

rdb = RunDb()
rdb.userdb.create_user('user00', 'user00', 'user00@user00.user00')
rdb.userdb.add_user_group('user00', 'group:approvers')
user = rdb.userdb.get_user('user00')
user['blocked'] = False
user['machine_limit'] = 100
rdb.userdb.users.save(user)
rdb.userdb.create_user('user01', 'user01','user01@user01.user01')
user = rdb.userdb.get_user('user01')
user['blocked'] = False
user['machine_limit'] = 100
rdb.userdb.users.save(user)
