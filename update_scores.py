import json
import re
import urllib2

from models import Level, OfficialScores, db


level_ids = dict()
levels = Level.query.all()
for level in levels:
    level_ids[level.internal_name] = level.level_id

site = urllib2.urlopen('http://nebula.zachtronicsindustries.com/spacechem/score')
scores = site.read()
deserialized = json.loads(scores)

for level in deserialized:
    # if a new level has been added, need to insert it first
    if level not in level_ids:
        new_level = Level()
        new_level.internal_name = level
        new_level.slug = level
        researchnet_pattern = re.compile(r'^published\-(\d+\-\d+)$')
        if researchnet_pattern.search(level):
            new_level.number = researchnet_pattern.search(level).groups()[0]
            new_level.name = 'ResearchNet Published '+new_level.number
            new_level.order1 = new_level.number.split('-')[0]
            new_level.order2 = new_level.number.split('-')[1]
            new_level.category = 'researchnet'
        else:
            new_level.number = 'X-X'
            new_level.name = 'Unknown Name'
        db.session.add(new_level)
        db.session.commit()
        level_ids[level] = new_level.level_id

    level_id = level_ids[level]
    scores = OfficialScores()
    scores.level_id = level_ids[level]
    scores.reactor_counts = deserialized[level]['ReactorCounts']
    scores.symbol_counts = deserialized[level]['SymbolCounts']
    scores.cycle_counts = deserialized[level]['CycleCounts']
    db.session.add(scores)

db.session.commit()
