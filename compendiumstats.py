# -*- coding: utf-8 -*-
'''
@author: dgorissen
'''
import os
import MySQLdb
import matplotlib
import matplotlib.mlab as mlab
import matplotlib.pyplot as mp
import matplotlib.dates as dates
import matplotlib.lines as lines
import numpy as np
from copy import deepcopy
from numpy import *
from datetime import datetime, date, timedelta
import csv


class CompendiumStats(object):
    """Connects to the compendium MySQL database and retrieves some statistics on the nodes it contains
       Compendium must be configured to use the MySQL backend for this to work."""
    
    def __init__(self, user=None, pwd=None, host=None):
        super(CompendiumStats,self).__init__()

        self.user = user
        self.pwd = pwd
        self.host = host
    
    def connect(self,db):        
        """connect to the the specified database"""
        conn = MySQLdb.connect (host = self.host,
                                user = self.user,
                                passwd = self.pwd,
                                db = db)
        
        return conn
        
    def list_projects(self):
        """Return a project name -> database name dictionary"""
        
        conn = self.connect("compendium")
        cursor = conn.cursor()
        cursor.execute("SELECT ProjectName,DatabaseNAme FROM project")

        proj = []
        for row in cursor:
            proj.append( (row[0],row[1]) )
        
        conn.close()
        
        return dict(proj)
    
    def gen_stats(self,project,result_dir,projectdb=None):
        """Generate csv & png files for a number of statistics about the nodes in the compendium database"""
        
        # resolve the project db
        if not projectdb:
            projs = self.list_projects()
            projectdb = projs[project]

        # connect to the project db
        self.conn = self.connect(projectdb)
        cursor = self.conn.cursor()
        
        # set the result dir, creating it if necessary
        self.result_dir = os.path.join(result_dir,project)
        if not os.path.exists(self.result_dir):
            os.makedirs(self.result_dir)
        
        # Get some DB stats, generate output in different files
     
        # Build Node type map
        note_types = ['List','Map','Question','Position','Argument','Pro','Con','Decision',
                     'Reference','Note','List_shortcut','Map_shortcut','Issue_shortcut',
                     'Position_shortcut','Argument_shortcut','Pro_shortcut','Con_shortcut',
                     'Decision_shortcut','Reference_shortcut','Note_shortcut'
                     ]
        
        node_type_map = dict(zip(range(1,len(note_types)+1),  ["Num_" + x for x in note_types]))
    
        # ==============================================================================================
        stats = {}
        
        # How many non-deleted nodes
        cursor.execute ("SELECT COUNT(*) FROM Node n, ViewNode vn WHERE n.NodeID = vn.NodeID and vn.CurrentStatus != 3")
        row = cursor.fetchone ()
        stats['NumNodes'] = row[0]
    
        # How many nodes of each type
        cursor.execute ("SELECT n.NodeType, COALESCE(COUNT(*),0) FROM Node n WHERE n.NodeType > 0 AND n.NodeType < 11 GROUP BY n.NodeType")
        stats = dict([(node_type_map[x[0]],x[1]) for x in cursor])
        
        self.write_stats("Node_Types", stats, figTitle="Number of node types")
    
        # ==============================================================================================
    
        # Tag statistics
        cursor.execute ("SELECT c.Name AS 'Tag', COALESCE(COUNT(*),0) AS 'Number of nodes' FROM Code c JOIN NodeCode nc ON c.CodeID = nc.CodeID GROUP BY c.CodeID")
        stats = dict([(x[0],x[1]) for x in cursor])
    
        self.write_stats("Tagged_Nodes", stats, figTitle="Number of tagged nodes")
        
        # ==============================================================================================
        stats = {}
    
        # Decisions without evidence
        cursor.execute ("SELECT DISTINCT COALESCE(COUNT(*),0) FROM " +
                        "(" +
                          "SELECT n.Author, n.Label, n.Detail, vn.ViewID, vn.CurrentStatus  FROM Node n " +
                          "JOIN ViewNode vn ON n.NodeID = vn.NodeID " +
                          "WHERE n.NodeType = 8 AND n.Detail = '' AND vn.CurrentStatus != 3" + 
                        ") AS tmp " +
                        "JOIN Node n2 ON tmp.ViewID = n2.NodeID")
        
        row = cursor.fetchone ()
        stats['DecisionsNoEvidence'] = row[0]
        
        # Unanswered questions
        cursor.execute ("SELECT DISTINCT COALESCE(COUNT(*),0) FROM " +
                        "(" +
                          "SELECT n.Author, n.Label, vn.ViewID, vn.CurrentStatus  FROM Node n " +
                          "JOIN ViewNode vn ON n.NodeID = vn.NodeID " +
                          "WHERE n.NodeType = 3 AND n.NodeID NOT IN (SELECT ToNode FROM Link) AND vn.CurrentStatus != 3" +
                        ") AS tmp " +
                        "JOIN Node n2 ON tmp.ViewID = n2.NodeID")
        row = cursor.fetchone ()
        stats['QuestionsNoAnswer'] = row[0]
    
        self.write_stats("Design_Queries", stats, figTitle="Design status queries")
    
        # ==============================================================================================
        # Number of nodes created by each user
        cursor.execute ("SELECT n.Author, COALESCE(COUNT(*),0) FROM Node n, ViewNode vn WHERE n.Author <> 'Administrator' AND n.NodeID = vn.NodeID AND vn.CurrentStatus != 3 GROUP BY Author")
        stats = dict([(x[0].replace(" ","_"),x[1]) for x in cursor])
    
        self.write_stats("User_Stats", stats, figTitle="Contributions per user")
    
        # ==============================================================================================
        # History of how many nodes were created/modified by each user on each day
    
        # we need to create a temp table first to handle days on which no nodes were created
        # they need to be represented as 0
        #select date_format(from_unixtime(CreationDate/1000),'%Y-%m-%d') cd, Author, count(*) from Node group by cd
        cursor.execute("CREATE TEMPORARY TABLE DateRange (d DATE NOT NULL)")
        startDate = date(2010, 3, 1)
        for day in self.datespan(startDate):
            cursor.execute("INSERT INTO DateRange (d) values('" + day.isoformat() + "')")
        
        # Prepare the author map
        cursor.execute("SELECT DISTINCT Author FROM node n WHERE Author <> 'Administrator'")
        authorMap = dict([(x[0],0) for x in cursor])

        self.genUserStats(cursor, authorMap, "CreationDate")
        self.genUserStats(cursor, authorMap, "ModificationDate")
    
        # ==============================================================================================
        
        cursor.close ()
        self.conn.close ()
    

    def genUserStats(self, cursor, authorMap, timeField):
        """Generate the statistics per user"""
        # TODO not the most efficient code :)
        
        # get the actual statistics
        cursor.execute("SELECT dr.d, n.Author, COALESCE(COUNT(*),0) as 'Num_Nodes'" 
                       + " From DateRange dr LEFT JOIN Node n ON dr.d = date_format(from_unixtime(n." + timeField + "/1000),'%Y-%m-%d')"
                       + " WHERE n.Author <> 'Administrator'"
                       + " GROUP BY dr.d, n.Author ORDER BY dr.d ASC")
        
        dateMap = {}
        # its important to ensure the value order in each row is correct
        for row in cursor:
            d = row[0]
            a = row[1]
            c = row[2]
    
            if(a == None):
                # nobody created any nodes on this day, add empty map (0 for all authors)
                dateMap[d] = deepcopy(authorMap)
            else:
                if(d in dateMap):
                    dateMap[d][a] = c
                else:
                    dateMap[d] = deepcopy(authorMap)
                    dateMap[d][a] = c
        
        # Now write the whole thing to file
        fname = os.path.join(self.result_dir, "User_Contribs_" + timeField + ".csv");
        file = open(fname,'w')
        
        headerList = map(lambda x : x.replace(" ","_"),sorted(authorMap.iterkeys())) 
        header = "Date," + ",".join(headerList)
        
        file.write(header + "\n")
             
        line = ""         
        for d in sorted(dateMap.iteritems()):
            # save as a timestamp matplotlib likes
            line = str(dates.date2num(d[0]))
            for k in sorted(d[1].iterkeys()):
                if(len(d[1]) > 12):
                    print d[1].keys()
                line += "," + str(d[1][k])
            file.write(line + "\n")
                 
        file.close()
        self.plot_stats([fname], figTitle="Historic contributions per user (" + timeField + ")")
    
    def write_stats(self, filename, stats, figTitle=""):    
        """Write the stats to a csv file"""   
        
        fname = os.path.join(self.result_dir, filename + ".csv");
        fileExists = os.path.isfile(fname)
    
        file = open(fname,'a')
        # add a timestamp
        #stats['time'] = datetime.now()
        stats['time'] = dates.date2num(datetime.now())
        fieldnames = sorted(stats.keys()[:]);
        # ensure the timestamp is always first
        fieldnames.remove("time")
        fieldnames = ["time"] + fieldnames 
        
        csvWriter = csv.DictWriter(file,fieldnames)
        
        if (not fileExists):
            # write the header
            file.write(','.join(fieldnames) + "\n")
            
        csvWriter.writerow(stats);
        file.close();
        
        # Now plot it
        self.plot_stats([fname], figTitle)
    
    def plot_stats(self, fileNames, figTitle=""):
        """ plot stats in the given csv file to a new file using matplotlib"""
            
        for fname in fileNames:
            # load the csv file
            r = np.genfromtxt(fname,delimiter=',',autostrip=True,skip_header=1)
            f = open(fname,'rU')
            labels = f.readline().split(',')
    
            #if(len(r.shape) == 1):
            #    continue
            
            # filled markers
            fmarkers = lines.Line2D.filled_markers
            colors = ['r', 'g', 'b', 'c', 'm' , 'k' ,'y']
            
            fig = mp.figure(figsize=(12,8))
            
            #dont plot anything if there is only one column
            if(r.ndim == 0 or len(labels) < 2):
                continue
            # if the file only contains one row
            elif(r.ndim == 1):
                #r = reshape(r,(1,r.size))
                for i in range(1,len(r)):
                    ax = mp.plot_date(r[0],r[i],label=labels[i],xdate=True,linestyle='-',marker=fmarkers[i%len(fmarkers)],color=colors[i%len(colors)])
            else:
                for i in range(1,r.shape[2-1]):
                    ax = mp.plot_date(r[:,0],r[:,i],label=labels[i],xdate=True,linestyle='-',marker=fmarkers[i%len(fmarkers)],color=colors[i%len(colors)])
            
            mp.xlabel('Time')
            mp.legend(labels[1:],loc='upper left')
    
            fig.gca().xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%d %b\n%H:%M'))
            mp.title(figTitle, fontsize=12)
            #matplotlib.pyplot.draw()
            #matplotlib.pyplot.show()
    
            # save the figure to disk
            figFile = fname[0:-4] + ".png"
            mp.savefig(figFile,bbox_inches='tight')
    
     
    def datespan(self, startDate, endDate=date.today(), delta=timedelta(days=1)):
        """Generate a sequence of dates"""
        currentDate = startDate
        while currentDate < endDate:
            yield currentDate
            currentDate += delta
    

if __name__ == '__main__':
    c = CompendiumStats(user="xx", pwd="xx", host="xx");

    # generate stats for every project in the database
    projs = c.list_projects()
    for name,db in projs.iteritems():
        c.gen_stats(name, ".", projectdb=db)

