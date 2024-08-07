<%page args="pages=None"/>

% if pages and len(pages) > 3:
  <nav aria-label="Pagination">
  <ul class="pagination pagination-sm">
  % for page in pages:
    <li class="page-item ${page['state']}">
      % if page['state'] not in ['disabled', 'active']:
        <a class="page-link" href="${page['url']}" aria-label="Page ${page['idx']}">${page['idx']}</a>
      % elif page['state'] == 'active':
        <a class="page-link" aria-current="page">${page['idx']}</a>
      % else:
        <a class="page-link" aria-disabled="true">${page['idx']}</a>
      % endif
    </li>
  % endfor
  </ul>
  </nav>
% endif
