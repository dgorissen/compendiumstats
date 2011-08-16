/*
  Simple proof-of-principle web interface to the compendium database
  Allows the user run predifined queries of intrest
*/

<?php
date_default_timezone_set('Europe/London');
//===========================================================================================
//== Database stuff

$dbhost = 'localhost';
$dbuser = 'foo';
$dbpass = 'bar';
$dbname = 'foo_bar';

$dbhandle = mysql_connect($dbhost, $dbuser, $dbpass) or die('Error connecting to MySQL');

mysql_select_db($dbname);
//echo "Connected to MySQL database " . $dbname . " on " . $dbhost . "<p>";

//select a database to work with
$selected = mysql_select_db($dbname,$dbhandle) 
  or die("Could not select the database");
//===========================================================================================
//== Form stuff

$activeFilter = $_POST["filters"];

//===========================================================================================
//Summary statistics of how many nodes there are for each tag
$queryTagStats = "SELECT c.Name AS 'Tag', COALESCE(COUNT(*),0) AS 'Number of nodes' FROM Code c " .
		 "JOIN NodeCode nc ON c.CodeID = nc.CodeID " .
		 "GROUP BY c.CodeID";

//Build the list of possible filters
$filterItems = prepareFilters($dbhandle);

//===========================================================================================
?>


<HTML><HEAD><TITLE>Compendium Query Tool</TITLE></HEAD>
<style type="text/css">
@import url("style.css");
</style>

<BODY>

<center>
  <h2>Compendium Query Tool</h2>

  <form method="post" action="<?php echo $PHP_SELF;?>">
    <em>Filter nodes on</em> :

    <?php

    //Generate the combobox of possible filters
    print("<select name='filters'>\n");

    foreach ($filterItems as $key => $value){
	$it = $filterItems[$key];

	if(strcmp($it->getId(),$activeFilter) == 0){
	    print("<option value='" . $it->getId() . "' selected='true'>" . $it->getDesc() . "</option>\n");
	}else{
	    print("<option value='" . $it->getId() . "'>" . $it->getDesc() . "</option>\n");
	}
    }

    print("</select>\n"); 
    ?>

    <input type="submit" value="submit" name="submit">
  </form> 
</center>
<hr />

<p />
<h2>Tag statistics</h2>
  <?php
    display_db_query($queryTagStats, $dbhandle, TRUE);
  ?>

<p />
<p />


<?php
  if (!isset($_POST['submit'])) {
    print("<p /><h3>Please select a filter from the combobox at the top of the page</h3>\n");
  }else{

      $it = $filterItems[$activeFilter];

      $filter = $it->getDesc();
      $q = $it->getQuery();
      $q = str_replace("#TAGID#",$activeFilter,$q);

      print("<h2>Nodes matching filter <font color='blue'>&lt;$filter&gt;</font></h2>\n"); 

      display_db_query($q, $dbhandle, TRUE);
      print("</BODY></HTML>\n"); 
  }
?>


<?php

//===========================================================================================
//== Helper functions/classes

//Utility class
class FilterItem {
  private $id;
  private $description;
  private $query;

  public function __construct($i,$desc,$q){
    $this->id = $i;
    $this->description = $desc;
    $this->query = $q;
  }

  public function __toString(){
        return $this->id . "_" . $this->description . "_" . $this->query . "\n";
  }

  public function getId(){ return $this->id;}
  public function getDesc(){ return $this->description;}
  public function getQuery(){ return $this->query;}
}

function prepareFilters($dbhandle){
  //Prepare the map of possible filters
  $filterItems = array();

  //Get all the currently defined tags
  $q = "SELECT CodeID, Name FROM Code";
  $result_id = doQuery($q,$dbhandle);

  //For each tag build the query that returns the nodes tagged by the tag including the map they are in
  while($row = mysql_fetch_row($result_id)) {

    //$d = getTagName($dbhandle,$activeFilter);

    $q = "SELECT DISTINCT n2.Label AS Map, tmp.Label AS 'Issue', tmp.Author FROM ".
	  "(" .
	    "SELECT n.Author, n.Label, vn.ViewID, vn.CurrentStatus FROM Node n " .
	    "JOIN ViewNode vn ON n.NodeID = vn.NodeID " .
	    "JOIN NodeCode nc ON n.NodeID = nc.NodeID " .
	    "WHERE nc.CodeID='" . $row[0] . "' AND vn.CurrentStatus != 3" .  //currentstatus -> dont show deleted nodes
	  ") AS tmp " .
	  "JOIN Node n2 ON tmp.ViewID = n2.NodeID " .
	  "ORDER BY Map";

    $filterItems[$row[0]] = new FilterItem($row[0],$row[1],$q);
  }

  //Add some custom ones

  //Which decisions dont have evidence (detail)
  $i = 'DecisionsNoEvidence';
  $d = 'Decisions without evidence';
  $q = "SELECT DISTINCT n2.Label AS Map, tmp.Label AS 'Issue', tmp.Author FROM ".
	"(" .
	  "SELECT n.Author, n.Label, n.Detail, vn.ViewID, vn.CurrentStatus  FROM Node n " .
	  "JOIN ViewNode vn ON n.NodeID = vn.NodeID " .
	  "WHERE n.NodeType = 8 AND n.Detail = '' AND vn.CurrentStatus != 3" . 
	") AS tmp " .
	"JOIN Node n2 ON tmp.ViewID = n2.NodeID " .
	"ORDER BY Map";
  $filterItems[$i] = new FilterItem($i,$d,$q);

  //select all questions that do not have any nodes pointing to them
  $i = 'QuestionsNoAnswer';
  $d = 'Unanswered Questions';
  $q = "SELECT DISTINCT n2.Label AS Map, tmp.Label AS 'Issue', tmp.Author FROM " .
	"(" .
	  "SELECT n.Author, n.Label, vn.ViewID, vn.CurrentStatus  FROM Node n " .
	  "JOIN ViewNode vn ON n.NodeID = vn.NodeID " .
	  "WHERE n.NodeType = 3 AND n.NodeID NOT IN (SELECT ToNode FROM Link) AND vn.CurrentStatus != 3" .
	") AS tmp " .
	"JOIN Node n2 ON tmp.ViewID = n2.NodeID " .
	"ORDER BY Map";
  $filterItems[$i] = new FilterItem($i,$d,$q);

  //select all orphaned (disconnected) nodes
  $i = 'Orphans';
  $d = 'Orphaned nodes';
  $q = "SELECT DISTINCT n2.Label AS Map, tmp.Label AS 'Issue', tmp.Author FROM " .
	"(" .
	  "SELECT n.Author, n.Label, vn.ViewID, vn.CurrentStatus FROM Node n " .
	  "JOIN ViewNode vn ON n.NodeID = vn.NodeID " .
	  "WHERE n.NodeID NOT IN (SELECT ToNode FROM Link) AND n.NodeID NOT IN (SELECT FromNode FROM Link) AND vn.CurrentStatus != 3" .
	") AS tmp " .
	"JOIN Node n2 ON tmp.ViewID = n2.NodeID " .
	"WHERE n2.NodeType != 1 AND tmp.Author != 'Administrator' AND n2.Label != 'Home Window' AND n2.Label != 'Decode'" . //ignore nodes in lists and nodes in welcome/intro/top level maps
	"ORDER BY Map";
  $filterItems[$i] = new FilterItem($i,$d,$q);

  //foreach ($filterItems as $key => $value){
  //  $it = $filterItems[$key];
  //  print $it . "<br><br>\n\n";
  //}

  return $filterItems;
}

function getTagName($connection, $tagID){
  $q = "SELECT Name FROM Code WHERE CodeID = '$tagID'";
  $result_id = doQuery($q, $connection);
  $row = mysql_fetch_row($result_id);

  if($row){
    return $row[0];
  }else{
    return "unknown";
  }
}

function doQuery($query_string, $connection){
  $result_id = mysql_query($query_string, $connection) or die("display_db_query:" . mysql_error());

  return $result_id;
}

//Source: http://scriptplayground.com/tutorials/php/Printing-a-MySQL-table-to-a-dynamic-HTML-table-with-PHP/
function display_db_query($query_string, $connection, $header_bool) {

	$result_id = doQuery($query_string, $connection);
	$table_params = "id='hor-zebra'";

	// find out the number of columns in result
	$column_count = mysql_num_fields($result_id)
	or die("display_db_query:" . mysql_error());
	// Here the table attributes from the $table_params variable are added
	print("<TABLE $table_params >\n");
	// optionally print a bold header at top of table
	if($header_bool) {
		print("<TH>#</TH>");
		for($column_num = 0; $column_num < $column_count; $column_num++) {
			$field_name = mysql_field_name($result_id, $column_num);
			print("<TH>$field_name</TH>");
		}
		print("</TR>\n");
	}
	// print the body of the table
	$ctr = 1;
	while($row = mysql_fetch_row($result_id)) {
		$col=$ctr%2;
		if($col == 1){
			print("<TR class='odd'>");
		}else{
			print("<TR class='even'>");
		}
		print("<TD>$ctr</TD>\n");$ctr++;
		for($column_num = 0; $column_num < $column_count; $column_num++) {
			print("<TD>$row[$column_num]</TD>\n");
		}
		print("</TR>\n");
	}
	print("</TABLE>\n"); 

}

?>
