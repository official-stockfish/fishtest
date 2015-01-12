<%inherit file="base.mak"/>
<script>
	$(document).ready(function() {
		$("#btn_save").on("click", function() {
			$("#result").html("Saving data...")
			jQuery.ajax({
				type:'POST',
				url:  "/regression/data?type=${test_type}",
				data: $("#data").val(),
				contentType: 'application/json; charset=utf-8',
				success: function() {
					$("#result").html("Saved!").css("color", "green");
				},
				error: function(xhr, ajaxOptions, thrownError) {
					$("#result").html(xhr.responseText);
				}
			});
		});
	});
</script>

<h3>Update regression data</h3>
<div>
Be very careful!
</div>
<div>
<textarea id="data" style="height: 400px; width: 900px;">${data}</textarea>
</div>
<div>
<button class="btn" id="btn_save">Save Data</button><div id="result"></div>
</div>