from pyramid.security import Allow, Everyone

class RootFactory(object):
  __acl__ = [ (Allow, Everyone, 'view'),
              (Allow, 'group:admins', 'modify_db'),
              (Allow, 'group:approvers', 'approve_run'), ]
  def __init__(self, request):
    pass

