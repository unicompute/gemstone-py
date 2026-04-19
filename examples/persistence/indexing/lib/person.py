"""
Port of persistence/indexing/lib/person.rb
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import random
from .address import Address

FIRST_NAMES_MALE   = ['James', 'John', 'Robert', 'Michael', 'William',
                       'David', 'Richard', 'Joseph', 'Thomas', 'Charles']
FIRST_NAMES_FEMALE = ['Mary', 'Patricia', 'Linda', 'Barbara', 'Elizabeth',
                       'Jennifer', 'Maria', 'Susan', 'Margaret', 'Dorothy']
LAST_NAMES         = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones',
                       'Garcia', 'Miller', 'Davis', 'Wilson', 'Taylor']
MARITAL_STATUS     = ['single', 'married', 'hermit']


class Person:
    def __init__(self, name, age, gender, address, marital_status='single'):
        self.name           = name
        self.age            = age
        self.gender         = gender
        self.address        = address
        self.marital_status = marital_status

    def __str__(self):
        return (f"{self.name} is a {self.age} year old, "
                f"{self.marital_status} {self.gender}, "
                f"and lives at: {self.address}")

    @classmethod
    def random(cls):
        gender = random.choice(['male', 'female'])
        first  = random.choice(FIRST_NAMES_MALE if gender == 'male' else FIRST_NAMES_FEMALE)
        last   = random.choice(LAST_NAMES)
        return cls(
            name           = f"{first} {last}",
            age            = random.randint(18, 92),
            gender         = gender,
            address        = Address.random(),
            marital_status = random.choice(MARITAL_STATUS),
        )
