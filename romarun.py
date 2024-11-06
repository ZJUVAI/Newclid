import os

need_aux = [
    "translated_imo_2008_p1_all_extras",
]


if __name__ == "__main__":
    for problem in need_aux:
        os.system(
            "geosolver --problem-name translated_imo_2008_p1_all_extras --problems-file ./problems_datasets/examples.txt --log-level 20"
        )
