from pyramid.security import Allow, Everyone

class RootFactory(object):
  __acl__ = [ (Allow, Everyone, 'view'),
              (Allow, 'group:admins', 'modify_db'),
              (Allow, 'group:approvers', 'approve_run'),
              (Allow, 'group:stats', 'modify_stats'), ]
  def __init__(self, request):
    pass

