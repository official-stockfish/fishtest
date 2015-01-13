<%inherit file="base.mak"/>
<style>
input[type=number]::-webkit-inner-spin-button,
input[type=number]::-webkit-outer-spin-button {
    -webkit-appearance: none;
    margin: 0;
}

td {
	padding: 5px;
	padding-left: 20px;
	border-bottom: 1px solid #ddd;
}
</style>

<h3>Update regression data</h3>

%if test_type == "fishtest":
	
	<div>Insert new data: </div>

	<form action="/regression/data/save?type=fishtest" method="post">
	<div class="form-group form-horizontal">
	   <input  class="form-control" style="width: 60px;" maxlength="7" id="input_commit" name="commit" type="text" placeholder="Commit" required>
	   <input  class="form-control" style="width: 150px;" id="input_date_committed" name="date_committed" type="text" placeholder="Commited Date" required>
	   <input  class="form-control" style="width: 200px;" id="input_link" type="text" name="link" placeholder="Fishtest Link" required>
	   <input  class="form-control" style="width: 60px;" id="input_elo" type="number" step="any" name="elo" placeholder="Elo" required>
	   <input  class="form-control" style="width: 60px;" id="input_error" type="number" step="any" name="error" placeholder="Error" required>
	   <button type="submit" class="btn btn-primary">Save</button>
	</div>
	</form>

	<table>
	<thead>
	<tr>
	    <td></td>
		<td><b>Commit</b></td>
		<td><b>Commited Date</b></td>
		<td><b>Link</b></td>
		<td><b>Elo</b></td>
		<td><b>Error</b></td>
	</tr>
	</thead>
	<tbody>
		%for item in data:
		<tr>
		<form action="/regression/data/delete?type=fishtest" method="post">
		<td>
			<input class="form-control" type="hidden" name="_id" value="${item['_id']}">
			<button type="submit" class="btn btn-danger">Delete</button>
		</td>
		</form>
		<td>${item['data']['commit']}</td>
		<td>${item['data']['date_committed']}</td>
		<td>${item['data']['link']}</td>
		<td>${item['data']['elo']}</td>
		<td>${item['data']['error']}</td>
		</tr>
		%endfor
	</tbody>
	</table>

%elif test_type == "jl":

	<form action="/regression/data/save?type=jl" method="post">
	<div class="form-group form-horizontal">
	   <input  class="form-control" style="width: 200px;" id="input_description" name="description" type="text" placeholder="Short Description" required>
	</div>

	<div class="form-group" style="padding-top: 10px;">
	Long description for this run:
	<div><textarea  class="form-control" id="textarea_long_description" name="long_description" style="width: 400px; height: 100px;"></textarea></div>
	</div>
	<div class="form-group" style="padding-top: 10px;">
	Data in CSV format: sha, date_committed, elo, error, points
	<div><textarea  class="form-control" id="textarea_data" name="data" style="width: 400px; height: 200px;" required></textarea></div>
	</div>
	<button type="submit" class="btn btn-primary">Save</button>
	</form>

	<table>
	<thead>
	<tr>
	    <td></td>
		<td><b>Description</b></td>
	</tr>
	</thead>
	<tbody>
		%for item in data:
		<tr>
		<form action="/regression/data/delete?type=jl" method="post">
		<td>
			<input class="form-control" type="hidden" name="_id" value="${item['_id']}">
			<button type="submit" class="btn btn-danger">Delete</button>
		</td>
		</form>
		<td>${item['data']['description']}</td>
		</tr>
		%endfor
	</tbody>
	</table>

%endif 

