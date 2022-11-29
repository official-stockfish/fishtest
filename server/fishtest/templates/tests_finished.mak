<%inherit file="base.mak"/>

<script>
  document.title =  'Finished Tests | Stockfish Testing';
</script>

<h2>
  Finished Tests
</h2>

<form class="row mb-3">
  <div class="col-12 col-md-auto mb-3">
    <label for="tc" class="form-label">Time control</label>
    <select id="tc" class="form-select" name="tc">
      <option value="">All</option>
      <option value="stc" ${"selected" if request.GET.get('tc') == "stc" else ''}>STC</option>
      <option value="ltc" ${"selected" if request.GET.get('tc') == "ltc" else ''}>LTC</option>
    </select>
  </div>

  <div class="col-12 col-md-auto mb-3">
    <label for="status" class="form-label">Status</label>
    <select id="status" class="form-select" name="status">
      <option value="">All</option>
      <option value="yellow" ${"selected" if request.GET.get('status') == "yellow" else ''}>Yellow</option>
      <option value="green" ${"selected" if request.GET.get('status') == "green" else ''}>Green</option>
    </select>
  </div>

  <div class="col-12 col-md-auto mb-3">
    <label for="info" class="form-label">Info</label>
    <input id="info" type="text" name="info" class="form-control" placeholder="Run info" value="${request.GET.get('info') if request.GET.get('info') is not None else ''}">
  </div>

  <div class="col-12 col-md-auto mb-3 d-flex align-items-end">
    <button type="submit" class="btn btn-success w-100">Search</button>
  </div>
</form>

<%include file="run_table.mak" args="runs=finished_runs,
                                     header='Finished',
                                     count=num_finished_runs,
                                     pages=finished_runs_pages"
/>
