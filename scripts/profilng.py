import os


problems = [
    "translated_imo_2000_p1",
    "translated_imo_2000_p6",
    "translated_imo_2002_p2a",
    "translated_imo_2002_p2b",
    "translated_imo_2003_p4",
    "translated_imo_2004_p1",
    "translated_imo_2004_p5",
    "translated_imo_2005_p5",
    "translated_imo_2007_p4",
    "translated_imo_2008_p1a",
    "translated_imo_2008_p1b",
    "translated_imo_2008_p6",
    "translated_imo_2009_p2",
    "translated_imo_2010_p2",
    "translated_imo_2010_p4",
    "translated_imo_2011_p6",
    "translated_imo_2012_p1",
    "translated_imo_2012_p5",
    "translated_imo_2013_p4",
    "translated_imo_2014_p4",
    "translated_imo_2015_p3",
    "translated_imo_2015_p4",
    "translated_imo_2016_p1",
    "translated_imo_2017_p4",
    "translated_imo_2018_p1",
    "translated_imo_2019_p2",
    "translated_imo_2019_p6",
    "translated_imo_2020_p1",
    "translated_imo_2021_p3",
    "translated_imo_2022_p4",
]

for problem in problems:
    os.system(f"mkdir -p profiling_exp/{problem}")
    os.system(f"mkdir -p profiling_opt/{problem}")
    os.system(
        f"python -m cProfile -o profiling_exp/{problem}/profile.prof -s cumulative -m newclid --problem-name {problem} --problems-file problems_datasets/imo_ag_30.txt --env profiling_exp"
    )
    os.system(
        f"python -m cProfile -o profiling_opt/{problem}/profile.prof -s cumulative -m newclid --problem-name {problem} --problems-file problems_datasets/imo_ag_30.txt --env profiling_opt"
    )
