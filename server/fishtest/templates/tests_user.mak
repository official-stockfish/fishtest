<%inherit file="base.mak"/>

<%def name="title_tests_user()">${username} | Stockfish Testing</%def>

<%block name="head">
  <meta property="og:title" content="${title_tests_user()}" />
</%block>

<h2>${username} - Info</h2>

<script>
  document.title = '${title_tests_user()}';
</script>

<%include file="run_tables.mak"/>
