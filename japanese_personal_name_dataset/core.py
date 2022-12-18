import csv
import os


def load_dataset(kind='org'):

    man_names = {}
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dataset/first_name_man_org.csv')) as f:
        reader = csv.reader(f)
        for row in reader:
            man_names[row[0]] = {
                'en': row[1],
                'kanji':row[2:]
            }


    woman_names = {}
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dataset/first_name_woman_org.csv')) as f:
        reader = csv.reader(f)
        for row in reader:
            woman_names[row[0]] = {
                'en': row[1],
                'kanji':row[2:]
            }

    return man_names, woman_names

if __name__ == '__main__':
    load_dataset()