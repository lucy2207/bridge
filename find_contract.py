def hand():
    diamonds = int(input("number of diamonds:"))
    hearts = int(input("number of hearts:"))
    clubs = int(input("number of clubs:"))
    spades = int(input("number of spades:"))
    points = int(input("number of points:"))

    return opening(diamonds, hearts, clubs, spades, points)

# 3 x -> 5-10 H + 7 cartes donts 2 honneurs
# bidding less than 12 pt : enchaires de barrages
#       bicolore cher: 1c 2p -> 5 coeurs 5 piques, 16 pts
# 5 piques, 5 coeurs, 4 carreaux, 4 trefles in that order
# if less than 12 -> enchaires aux barrages

def opening(diamonds, hearts, clubs, spades, points):
    suits = {
        "Diamonds": diamonds,
        "Hearts": hearts,
        "Spades": spades,
        "Clubs": clubs
    }

    if points < 12:
        return "Pass" # change later enchaires de barrages 
    
#    check for suits

#    1. if spades >= 5 -> 1 spades
#    2. if hearts >= 5 -> 1 hearts
#    3. if diamonds >= 4 -> 1 diamonds
#    4. if clubs >= 4 -> 1 clubs

    if 12 <= points <= 17:
        if len(spades) >= 5:
            first_bid = "1 Spades"
            return first_bid
        elif len(hearts) >= 5:
            first_bid = "1 Hearts"
            return first_bid
        elif len(diamonds) >= 4:
            first_bid = "1 Diamonds"
            return first_bid
        elif len(clubs) >= 4:
            first_bid = "1 Clubs"
            return first_bid
        else:
            return "No majors or minors"

#    where no suits present -> is balanced ?

#    is balanced = True

#    if 15-17 pts -> 
#    if 12-15 pts -> 
#    if 18-23 pts -> 

    is_balanced = True
    for suit in suits:
        if suits[suit] < 2 or suits[suit] > 5:
            is_balanced = False

    if is_balanced and points >= 15 and points <= 17:
        return "1 Sans Atouts"

#   is balanced = False

#    if 15-17 pts -> 
#    if 12-15 pts -> 
#    if 18-23 pts -> 



if __name__=="__main__":
    print("Welcome to bridge bidding 101")
    print(hand())
