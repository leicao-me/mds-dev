"""
Short script to automate creation of geojson file to visualize neighborhood
level counts of available bikes.

Usage: python create_neighborhood_counts.py user password database

Requires making a directory called neighborhood_counts in the same folder as this file.

Written by: David Klinger
"""

from measure import measure
import argparse
import fiona
import pprint
import json
import pyproj
import sqlalchemy
import datetime
import time
import shapely.ops
import shapely.geometry
import pandas
import functools
from mapboxgl.viz import *
from mapboxgl.utils import *

parser = argparse.ArgumentParser()
parser.add_argument("user", type=str,
        help="username to access postgresql database")
parser.add_argument("password", type=str,
        help="password to access postgresql database")
parser.add_argument("database", type=str,
        help="database name")
parser.add_argument("--host","-H", type=str,
        help="database host")
parser.add_argument("--port","-p", type=str,
        help="database port")
args = parser.parse_args()

# connect to database
def connect(user, password, db, host, port):
    url = 'postgresql://{}:{}@{}:{}/{}'
    url = url.format(user,password,host,port,db)
    con = sqlalchemy.create_engine(url)
    return con

user = args.user
password = args.password
db = args.database
host = "localhost"
if args.host is not None:
    host = args.host
port = 5432
if args.port is not None:
    port = args.port
con = connect(user,password,db,host,port)

def read_poly(poly, original, dest):
    interior = []
    exterior = []
    for p in poly:
        new_list = []
        for x,y in p:
            x_prime, y_prime = pyproj.transform(original, dest, x, y)
            p = (x_prime, y_prime)
            new_list.append(p)
        if exterior == []:
            exterior = new_list
        else:
            interior.append(new_list)
    final_area = shapely.geometry.Polygon(exterior, interior)
    return final_area


def get_equal_area(neighborhood):
    projection = functools.partial(pyproj.transform, 
                                   pyproj.Proj(init='epsg:4326'),
                                   pyproj.Proj("+proj=laea +lat_0=5 +lon_0=19 +x_0=0 +y_0=0 +ellps=WGS84 +units=m +no_defs "))
    return shapely.ops.transform(projection, neighborhood)

area = fiona.open("../data/shapefiles/la_neighborhoods.shp")
original = pyproj.Proj(area.crs, preserve_units=True)
dest = pyproj.Proj(init='epsg:4326')

start_time = datetime.datetime(2018,8,15,0,0,0)
start = time.mktime(start_time.timetuple())
end = time.mktime(datetime.datetime(2018,8,16,0,0,0).timetuple())
print("Querying.")
command = """
          SELECT * FROM "availability" 
          WHERE ((start_time < {} AND end_time > {}) OR
                 (start_time < {} AND end_time > {}) OR
                 (start_time > {} AND end_time < {})) AND
                 device_type = 'scooter'
          ORDER BY start_time, end_time
          """.format(start, start, end, end, start, end)
db = pandas.read_sql(command,con,index_col=None)
print("Query done.")
d = {}
d['type'] = 'FeatureCollection'
d['features'] = []
for a in area:
    if a['properties']['COMTY_NAME'] != "":
        f = {}
        f['type'] = 'Feature'
        f['geometry'] = {}
        f['geometry']['type'] = 'Polygon'
        f['geometry']['coordinates'] = []
        for l in a['geometry']['coordinates']:
            li = []
            for x,y in l:
                x_prime, y_prime = pyproj.transform(original, dest, x, y)
                li.append([x_prime,y_prime])
            f['geometry']['coordinates'].append(li)
        f['properties'] = {}
        f['properties']['name'] = a['properties']['COMTY_NAME']
        print("{}: {} of {}".format(f['properties']['name'],
                                    a['id'],
                                    len(area)))
        f['properties']['id'] = a['id']
        neighborhood = read_poly(a['geometry']['coordinates'],original,dest)
        # NOTE: THESE COUNTS ARE NORMALIZED BY AREA (sq. mi.)
        equal_area = get_equal_area(neighborhood)
        count = measure(db,start,end,neighborhood,False)/(equal_area.area/1609.344)
        f['properties']['count'] = count
        d['features'].append(f)
print("writing to file")
with open('neighborhood_counts/neighborhood.geojson','w') as f:
    json.dump(obj=d,fp=f,indent=4)
print("done")
print("\n")


