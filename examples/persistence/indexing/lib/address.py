"""
Port of persistence/indexing/lib/address.rb
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import random

STREETS = ['Main', 'Spruce', 'Robinson Ln', 'Taylor Ave', '43rd Ave']
CITIES  = ['Portland', 'AnyTown', 'Roseville', 'Santa Cruz', 'Bellingham',
            'Fort Collins', 'Berkeley', 'Yuma', 'Tucson', 'Vermillion', 'St. Louis']
STATES  = ['AZ', 'CA', 'CO', 'MO', 'WA', 'OR', 'SD']
ZIPS    = [12345, 23456, 34567, 45678, 56789, 67890]


class Address:
    def __init__(self, number, street, city, state, zip_code):
        self.number   = number
        self.street   = street
        self.city     = city
        self.state    = state
        self.zip_code = zip_code

    def __str__(self):
        return f"{self.number} {self.street}, {self.city}, {self.state}  {self.zip_code}"

    @classmethod
    def random(cls):
        return cls(
            number   = random.randint(1, 9500),
            street   = random.choice(STREETS),
            city     = random.choice(CITIES),
            state    = random.choice(STATES),
            zip_code = random.choice(ZIPS),
        )
