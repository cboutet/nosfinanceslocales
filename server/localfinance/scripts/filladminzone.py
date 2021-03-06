import os
import sys
import transaction

from fiona import collection
from shapely.geometry import shape, MultiPolygon
from shapely.ops import cascaded_union
from shapely.wkt import loads

from sqlalchemy import engine_from_config, func

from pyramid.paster import (
    get_appsettings,
    setup_logging,
    )

from ..models import (
    DBSession,
    AdminZone,
    Base,
    ADMIN_LEVEL_CITY,
    ADMIN_LEVEL_CITY_ARR,
    SRID,
    )

def usage(argv):
    cmd = os.path.basename(argv[0])
    print('usage: %s <config_uri> <filepath>\n'
          '(example: "%s development.ini")' % (cmd, cmd))
    sys.exit(1)

def extract_adminzone_data(city):
    properties = city['properties']
    g = shape(city['geometry'])
    if g.type == 'Polygon':
        g = MultiPolygon([g])
    admin_level = ADMIN_LEVEL_CITY
    if '-ARRONDISSEMENT' in properties['NOM_COMM']:
        admin_level = ADMIN_LEVEL_CITY_ARR
    return {'name': properties['NOM_COMM'],
            'population': properties['POPULATION'] * 1000,
            'code_department': properties['CODE_DEPT'],
            'code_city': properties['CODE_COMM'],
            'admin_level': admin_level,
            'geometry': "SRID=%s;"%SRID + g.wkt}

def main(argv=sys.argv):
    if len(argv) < 2:
        usage(argv)
    config_uri = argv[1]
    filepath = argv[2]
    setup_logging(config_uri)
    settings = get_appsettings(config_uri)
    engine = engine_from_config(settings, 'sqlalchemy.')
    DBSession.configure(bind=engine)
    Base.metadata.create_all(engine)
    with transaction.manager:
        # script
        with collection(filepath) as cities:
            for city in cities:
                data = extract_adminzone_data(city)
                az = AdminZone(**data)
                DBSession.add(az)

    cities_with_arr = [
        {'name': 'PARIS',
         'code_city': '056',
         'code_department': '75'},
        {'name': 'MARSEILLE',
         'code_city': '055',
         'code_department': '13'},
        {'name': 'LYON',
         'code_city': '123',
         'code_department': '69'}
    ]
    with transaction.manager:
        for city in cities_with_arr:
            wkt_geoms, populations = zip(*DBSession.query(func.ST_AsText(AdminZone.geometry), AdminZone.population)\
                .filter(AdminZone.name.contains(city['name']))\
                .filter(AdminZone.admin_level==ADMIN_LEVEL_CITY_ARR)\
                .all())
            city_geom = cascaded_union([loads(wkt_geom) for wkt_geom in wkt_geoms])
            if city_geom.type == 'Polygon':
                city_geom = MultiPolygon([city_geom])
            az = AdminZone(
                geometry="SRID=%s;"%SRID + city_geom.wkt, admin_level=ADMIN_LEVEL_CITY,
                name=city['name'], code_city=city['code_city'],
                code_department=city['code_department'],
                population=sum(populations),
                )
            DBSession.add(az)

if __name__ == '__main__':
    main()
