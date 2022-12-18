import csv



def load_dataset():

    man_names = {}
    with open('japanese_personal_name_dataset/dataset/first_name_man_org.csv') as f:
        reader = csv.reader(f)
        for row in reader:
            man_names[row[0]] = {
                'en': row[1],
                'kanji':row[2:]
            }


    woman_names = {}
    with open('japanese_personal_name_dataset/dataset/first_name_woman_org.csv') as f:
        reader = csv.reader(f)
        for row in reader:
            woman_names[row[0]] = {
                'en': row[1],
                'kanji':row[2:]
            }

    return man_names, woman_names

if __name__ == '__main__':
    load_dataset()