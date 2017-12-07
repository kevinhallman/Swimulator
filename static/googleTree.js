google.load("visualization", "1", {packages:["treemap"]});
google.setOnLoadCallback(drawChart);
function drawChart() {
    var data = google.visualization.DataTable("static/conf.json");
    tree = new google.visualization.TreeMap(document.getElementById('chart'));
    
	tree.draw(data, {
		minColor: '#f00',
		midColor: '#ddd',
		maxColor: '#0d0',
		headerHeight: 15,
		fontColor: 'black',
		showScale: true
    });
}
