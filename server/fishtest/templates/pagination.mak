<%page args="pages=None"/>

% if pages and len(pages) > 3:
  <nav>
  <ul class="pagination pagination-sm">
  % for page in pages:
    <li class="page-item ${page['state']}">
      % if page['state'] not in ['disabled', 'active']:
        <a class="page-link" href="${page['url']}">${page['idx']}</a>
      % else:
        <a class="page-link">${page['idx']}</a>
      % endif
    </li>
  % endfor
  </ul>
  </nav>
% endif
