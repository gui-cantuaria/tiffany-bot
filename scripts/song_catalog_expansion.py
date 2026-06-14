# Catálogo: artista -> faixas de extremo sucesso (expansão +3000)
ARTIST_HITS: dict[str, list[str]] = {
    "Michael Jackson": [
        "Billie Jean", "Thriller", "Beat It", "Smooth Criminal", "Black Or White",
        "Man In The Mirror", "Don't Stop Til You Get Enough", "The Way You Make Me Feel",
        "Rock With You", "Human Nature", "Remember The Time", "They Don't Care About Us",
    ],
    "Madonna": [
        "Like A Prayer", "Vogue", "Hung Up", "Material Girl", "Like A Virgin",
        "Papa Don't Preach", "Into The Groove", "La Isla Bonita", "Frozen", "Ray Of Light",
        "Music", "Holiday", "Express Yourself", "Take A Bow",
    ],
    "Prince": [
        "Purple Rain", "When Doves Cry", "Kiss", "1999", "Little Red Corvette",
        "Raspberry Beret", "Let's Go Crazy", "I Would Die 4 U", "Cream", "Diamonds And Pearls",
    ],
    "Whitney Houston": [
        "I Will Always Love You", "I Wanna Dance With Somebody", "Greatest Love Of All",
        "How Will I Know", "I Have Nothing", "Run To You", "One Moment In Time", "Queen Of The Night",
    ],
    "Mariah Carey": [
        "All I Want For Christmas Is You", "We Belong Together", "Hero", "Without You",
        "Fantasy", "Always Be My Baby", "Vision Of Love", "Emotions", "Honey", "Obsessed",
    ],
    "Celine Dion": [
        "My Heart Will Go On", "Because You Loved Me", "The Power Of Love", "It's All Coming Back To Me Now",
        "That's The Way It Is", "I'm Alive", "All By Myself", "To Love You More",
    ],
    "Britney Spears": [
        "Toxic", "...Baby One More Time", "Oops I Did It Again", "Womanizer", "Circus",
        "Gimme More", "Everytime", "Stronger", "Crazy", "Till The World Ends",
    ],
    "Christina Aguilera": [
        "Beautiful", "Genie In A Bottle", "Fighter", "Hurt", "Ain't No Other Man",
        "Candyman", "Dirrty", "Say Something ft A Great Big World", "Lady Marmalade",
    ],
    "Beyonce": [
        "Crazy In Love", "Halo", "Single Ladies", "Drunk In Love", "Formation",
        "Run The World", "Love On Top", "Irreplaceable", "If I Were A Boy", "Break My Soul",
        "Texas Hold Em", "16 Carriages", "Partition", "Sorry",
    ],
    "Rihanna": [
        "Umbrella", "We Found Love", "Diamonds", "Work", "Only Girl",
        "Stay", "Disturbia", "Rude Boy", "Needed Me", "Lift Me Up", "Bitch Better Have My Money",
    ],
    "Lady Gaga": [
        "Bad Romance", "Poker Face", "Shallow", "Just Dance", "Born This Way",
        "Telephone", "Million Reasons", "Rain On Me", "Paparazzi", "Alejandro", "Die With A Smile",
    ],
    "Katy Perry": [
        "Firework", "Roar", "Dark Horse", "Teenage Dream", "California Gurls",
        "Hot N Cold", "I Kissed A Girl", "E.T.", "Part Of Me", "Last Friday Night",
    ],
    "Taylor Swift": [
        "Shake It Off", "Blank Space", "Anti-Hero", "Cruel Summer", "Love Story",
        "You Belong With Me", "Look What You Made Me Do", "Cardigan", "All Too Well",
        "We Are Never Ever Getting Back Together", "Style", "Wildest Dreams", "Fortnight",
    ],
    "Adele": [
        "Rolling In The Deep", "Someone Like You", "Hello", "Set Fire To The Rain",
        "Easy On Me", "When We Were Young", "Send My Love", "Rumour Has It", "Skyfall",
    ],
    "Bruno Mars": [
        "Uptown Funk", "Just The Way You Are", "Locked Out Of Heaven", "When I Was Your Man",
        "24K Magic", "That's What I Like", "Grenade", "Treasure", "The Lazy Song",
    ],
    "Justin Timberlake": [
        "Cry Me A River", "SexyBack", "Mirrors", "Can't Stop The Feeling", "What Goes Around",
        "Rock Your Body", "Suit And Tie", "My Love", "Summer Love",
    ],
    "Usher": [
        "Yeah", "DJ Got Us Fallin In Love", "Burn", "U Got It Bad", "OMG",
        "Confessions Part II", "Love In This Club", "Scream", "My Way",
    ],
    "Alicia Keys": [
        "Fallin", "No One", "Girl On Fire", "If I Ain't Got You", "Empire State Of Mind",
        "You Don't Know My Name", "Un-thinkable", "Try Sleeping With A Broken Heart",
    ],
    "John Legend": [
        "All Of Me", "Ordinary People", "Save Room", "Glory", "Tonight",
        "Love Me Now", "You And I", "Green Light",
    ],
    "Sam Smith": [
        "Stay With Me", "Unholy", "Too Good At Goodbyes", "I'm Not The Only One",
        "Lay Me Down", "Dancing With A Stranger", "Writing's On The Wall",
    ],
    "Harry Styles": [
        "As It Was", "Watermelon Sugar", "Sign Of The Times", "Adore You",
        "Late Night Talking", "Music For A Sushi Restaurant", "Golden",
    ],
    "One Direction": [
        "What Makes You Beautiful", "Story Of My Life", "Best Song Ever", "Drag Me Down",
        "Night Changes", "Steal My Girl", "History",
    ],
    "Coldplay": [
        "Yellow", "Fix You", "Viva La Vida", "The Scientist", "Clocks",
        "Paradise", "Adventure Of A Lifetime", "Something Just Like This", "A Sky Full Of Stars",
        "Hymn For The Weekend", "Speed Of Sound", "Magic",
    ],
    "U2": [
        "With Or Without You", "One", "Beautiful Day", "Where The Streets Have No Name",
        "I Still Haven't Found What I'm Looking For", "Vertigo", "Sunday Bloody Sunday",
    ],
    "Radiohead": [
        "Creep", "Karma Police", "No Surprises", "Paranoid Android", "Fake Plastic Trees",
        "High And Dry", "Street Spirit", "Idioteque", "Lotus Flower",
    ],
    "Foo Fighters": [
        "Everlong", "The Pretender", "Best Of You", "Learn To Fly", "Times Like These",
        "All My Life", "My Hero", "Monkey Wrench",
    ],
    "Red Hot Chili Peppers": [
        "Under The Bridge", "Californication", "Can't Stop", "Scar Tissue", "Otherside",
        "Dani California", "Snow Hey Oh", "Give It Away", "By The Way",
    ],
    "Nirvana": [
        "Smells Like Teen Spirit", "Come As You Are", "Heart-Shaped Box", "Lithium",
        "In Bloom", "All Apologies", "About A Girl", "The Man Who Sold The World",
    ],
    "Pearl Jam": [
        "Alive", "Black", "Jeremy", "Even Flow", "Yellow Ledbetter",
        "Better Man", "Last Kiss", "Daughter",
    ],
    "Green Day": [
        "Basket Case", "American Idiot", "Boulevard Of Broken Dreams", "Wake Me Up When September Ends",
        "Good Riddance", "21 Guns", "Holiday", "When I Come Around",
    ],
    "Linkin Park": [
        "In The End", "Numb", "What I've Done", "Crawling", "Somewhere I Belong",
        "Breaking The Habit", "One Step Closer", "Heavy ft Kiiara",
    ],
    "Metallica": [
        "Enter Sandman", "Nothing Else Matters", "One", "Master Of Puppets",
        "The Unforgiven", "Fade To Black", "For Whom The Bell Tolls", "Sad But True",
    ],
    "Guns N Roses": [
        "Sweet Child O Mine", "November Rain", "Welcome To The Jungle", "Paradise City",
        "Don't Cry", "Patience", "Knockin On Heaven's Door",
    ],
    "AC/DC": [
        "Back In Black", "Highway To Hell", "Thunderstruck", "You Shook Me All Night Long",
        "TNT", "Shoot To Thrill", "Hells Bells",
    ],
    "Queen": [
        "Bohemian Rhapsody", "Don't Stop Me Now", "Another One Bites The Dust",
        "We Will Rock You", "We Are The Champions", "Somebody To Love", "Under Pressure",
        "Killer Queen", "Radio Ga Ga", "I Want To Break Free",
    ],
    "The Beatles": [
        "Hey Jude", "Let It Be", "Come Together", "Yesterday", "Here Comes The Sun",
        "Something", "Twist And Shout", "Help", "A Hard Day's Night", "In My Life",
    ],
    "The Rolling Stones": [
        "Paint It Black", "Gimme Shelter", "Sympathy For The Devil", "Angie",
        "Start Me Up", "Wild Horses", "Beast Of Burden", "Miss You",
    ],
    "Pink Floyd": [
        "Another Brick In The Wall", "Wish You Were Here", "Comfortably Numb",
        "Money", "Time", "Shine On You Crazy Diamond", "Hey You",
    ],
    "Led Zeppelin": [
        "Stairway To Heaven", "Whole Lotta Love", "Immigrant Song", "Black Dog",
        "Kashmir", "Ramble On", "Rock And Roll", "Going To California",
    ],
    "The Eagles": [
        "Hotel California", "Take It Easy", "Desperado", "Life In The Fast Lane",
        "New Kid In Town", "One Of These Nights", "Lyin Eyes",
    ],
    "Fleetwood Mac": [
        "Dreams", "Go Your Own Way", "The Chain", "Landslide", "Everywhere",
        "Rhiannon", "Little Lies", "Gypsy",
    ],
    "Bob Marley": [
        "Three Little Birds", "No Woman No Cry", "Redemption Song", "Is This Love",
        "Could You Be Loved", "Jamming", "One Love", "Stir It Up",
    ],
    "Eminem": [
        "Lose Yourself", "Without Me", "The Real Slim Shady", "Love The Way You Lie",
        "Stan", "Not Afraid", "Rap God", "Mockingbird", "Godzilla", "Houdini",
    ],
    "Jay-Z": [
        "Empire State Of Mind", "99 Problems", "Big Pimpin", "Hard Knock Life",
        "Run This Town", "Holy Grail", "Ni**as In Paris", "Crazy In Love",
    ],
    "Kanye West": [
        "Stronger", "Gold Digger", "Heartless", "Power", "All Of The Lights",
        "Touch The Sky", "Jesus Walks", "Through The Wire", "Flashing Lights",
    ],
    "Drake": [
        "God's Plan", "One Dance", "Hotline Bling", "In My Feelings", "Passionfruit",
        "Started From The Bottom", "Hold On We're Going Home", "Nice For What", "Fair Trade",
    ],
    "Kendrick Lamar": [
        "HUMBLE", "Alright", "DNA", "Swimming Pools", "Bitch Don't Kill My Vibe",
        "Money Trees", "King Kunta", "All The Stars", "tv off",
    ],
    "Travis Scott": [
        "SICKO MODE", "goosebumps", "Antidote", "FEIN", "Highest In The Room",
        "STARGAZING", "90210", "Butterfly Effect",
    ],
    "Future": [
        "Mask Off", "Life Is Good", "Low Life", "Turn On The Lights", "Where Ya At",
        "March Madness", "WAIT FOR U",
    ],
    "21 Savage": [
        "Bank Account", "a lot", "Rockstar", "No Heart", "Rich Flex",
        "Creepin", "Runnin",
    ],
    "Metro Boomin": [
        "Creepin", "Superhero", "Too Many Nights", "Space Cadet",
    ],
    "Lil Wayne": [
        "A Milli", "Lollipop", "6 Foot 7 Foot", "How To Love", "Mrs Officer",
        "Love Me", "Mirror ft Bruno Mars",
    ],
    "Nicki Minaj": [
        "Super Bass", "Anaconda", "Starships", "Moment 4 Life", "Beez In The Trap",
        "Chun-Li", "Barbie World", "Only",
    ],
    "Cardi B": [
        "Bodak Yellow", "I Like It", "WAP", "Please Me", "Money",
        "Be Careful", "Up",
    ],
    "Megan Thee Stallion": [
        "Savage", "WAP", "Body", "Hot Girl Summer", "Plan B",
        "HISS", "Mamushi",
    ],
    "SZA": [
        "Kill Bill", "Snooze", "Good Days", "The Weekend", "All The Stars",
        "Love Galore", "Broken Clocks", "Drew Barrymore",
    ],
    "Frank Ocean": [
        "Thinkin Bout You", "Pink White", "Ivy", "Nights", "Lost",
        "Channel", "Self Control",
    ],
    "The Weeknd": [
        "Earned It", "Often", "Wicked Games", "In Your Eyes", "Out Of Time",
        "Take My Breath", "Popular", "One Of The Girls",
    ],
    "Dua Lipa": [
        "New Rules", "Don't Start Now", "Physical", "Break My Heart",
        "IDGAF", "Be The One", "Houdini", "Training Season",
    ],
    "Calvin Harris": [
        "Summer", "Feel So Close", "This Is What You Came For", "One Kiss",
        "How Deep Is Your Love", "Promises", "My Way", "Slide",
    ],
    "David Guetta": [
        "Titanium", "When Love Takes Over", "Memories", "Without You",
        "Turn Me On", "Where Them Girls At", "Hey Mama", "Baby Don't Hurt Me",
    ],
    "Avicii": [
        "Wake Me Up", "Levels", "The Nights", "Waiting For Love", "Hey Brother",
        "Addicted To You", "Without You", "Seek Bromance",
    ],
    "Swedish House Mafia": [
        "Don't You Worry Child", "Save The World", "Greyhound", "Moth To A Flame",
        "It Gets Better",
    ],
    "Martin Garrix": [
        "Animals", "In The Name Of Love", "Scared To Be Lonely", "High On Life",
        "Summer Days",
    ],
    "Tiësto": [
        "Red Lights", "The Business", "Adagio For Strings", "Jackie Chan",
        "Don't Be Shy",
    ],
    "Skrillex": [
        "Bangarang", "Where Are U Now", "Scary Monsters And Nice Sprites",
        "First Of The Year", "Summit",
    ],
    "Daft Punk": [
        "Get Lucky", "One More Time", "Harder Better Faster Stronger", "Around The World",
        "Instant Crush", "Something About Us", "Digital Love",
    ],
    "The Chainsmokers": [
        "Closer", "Don't Let Me Down", "Something Just Like This", "Roses",
        "Paris", "#SELFIE",
    ],
    "Marshmello": [
        "Happier", "Alone", "Silence", "Friends", "Wolves", "Come and Go",
    ],
    "Shakira": [
        "Hips Don't Lie", "Waka Waka", "Whenever Wherever", "She Wolf",
        "La Tortura", "Chantaje", "TQG", "BZRP Music Sessions 53",
    ],
    "Bad Bunny": [
        "Tití Me Preguntó", "Dakiti", "MIA", "Yo Perreo Sola", "Me Porto Bonito",
        "Where She Goes", "Monaco", "Safaera", "Callaita",
    ],
    "J Balvin": [
        "Mi Gente", "Ginza", "Ay Vamos", "X", "Safari", "Que Pretendes",
        "In Da Getto", "6 AM",
    ],
    "Maluma": [
        "Felices Los 4", "Hawái", "Corazón", "Borro Cassette", "Mala Mía",
    ],
    "Ozuna": [
        "Criminal", "Se Preparó", "Baila Baila Baila", "La Modelo", "Caramelo",
    ],
    "Karol G": [
        "TQG", "Provenza", "Bichota", "Mamiii", "Ojitos Lindos",
        "Ahora Me Llama", "Mi Ex Tenía Razón",
    ],
    "Rosalía": [
        "MALAMENTE", "DESPECHÁ", "Con Altura", "LA FAMA", "BIZCOCHITO",
    ],
    "Rauw Alejandro": [
        "Desesperados", "Todo De Ti", "Punto 40", "Party", "Dile A El",
    ],
    "Anitta": [
        "Envolver", "Girl From Rio", "Me Gusta", "Versions Of Me", "Show Me The Money",
    ],
    "BTS": [
        "Dynamite", "Butter", "Boy With Luv", "DNA", "Spring Day",
        "Fake Love", "Blood Sweat Tears", "Life Goes On", "Permission To Dance",
    ],
    "BLACKPINK": [
        "DDU-DU DDU-DU", "Kill This Love", "How You Like That", "Pink Venom",
        "Shut Down", "As If It's Your Last", "Lovesick Girls",
    ],
    "PSY": [
        "Gangnam Style", "Gentleman", "Daddy", "That That",
    ],
    "TWICE": [
        "Fancy", "Feel Special", "Cheer Up", "TT", "Talk That Talk",
    ],
    "NewJeans": [
        "Hype Boy", "Ditto", "OMG", "Super Shy", "Attention", "ETA",
    ],
    "Stray Kids": [
        "God's Menu", "Back Door", "Maniac", "S-Class", "Thunderous",
    ],
    "SEVENTEEN": [
        "Super", "Don't Wanna Cry", "Very Nice", "Left Right", "Rock with you",
    ],
    "Burna Boy": [
        "Last Last", "Ye", "Anybody", "On The Low", "City Boys", "Gbona",
    ],
    "Wizkid": [
        "Essence", "Ojuelegba", "Come Closer", "Joro", "Smile",
    ],
    "Davido": [
        "Fall", "If", "Unavailable", "FIA", "Dami Duro",
    ],
    "Rema": [
        "Calm Down", "Dumebi", "Soundgasm", "Ozeba",
    ],
    "CKay": [
        "Love Nwantiti", "Emiliana", "Watawi",
    ],
    "Tems": [
        "Free Mind", "Essence", "Try Me", "Me & U",
    ],
    "Elvis Presley": [
        "Can't Help Falling In Love", "Suspicious Minds", "Jailhouse Rock", "Hound Dog",
        "Love Me Tender", "Burning Love", "In The Ghetto", "A Little Less Conversation",
    ],
    "Frank Sinatra": [
        "My Way", "Fly Me To The Moon", "New York New York", "Strangers In The Night",
        "That's Life", "Summer Wind", "The Way You Look Tonight",
    ],
    "Aretha Franklin": [
        "Respect", "Natural Woman", "Think", "I Say A Little Prayer", "Chain Of Fools",
    ],
    "Stevie Wonder": [
        "Superstition", "Isn't She Lovely", "I Just Called To Say I Love You", "Signed Sealed Delivered",
        "Sir Duke", "For Once In My Life", "Living For The City",
    ],
    "Marvin Gaye": [
        "What's Going On", "Sexual Healing", "Let's Get It On", "Ain't No Mountain High Enough",
        "Inner City Blues", "Mercy Mercy Me",
    ],
    "Al Green": [
        "Let's Stay Together", "Tired Of Being Alone", "Love And Happiness", "Take Me To The River",
    ],
    "Otis Redding": [
        "Sittin On The Dock Of The Bay", "Try A Little Tenderness", "These Arms Of Mine",
    ],
    "Ray Charles": [
        "Hit The Road Jack", "Georgia On My Mind", "I Can't Stop Loving You", "What'd I Say",
    ],
    "James Brown": [
        "I Got You I Feel Good", "Papa's Got A Brand New Bag", "It's A Man's Man's Man's World",
    ],
    "Earth Wind and Fire": [
        "September", "Boogie Wonderland", "Let's Groove", "After The Love Has Gone", "Fantasy",
    ],
    "Kool and The Gang": [
        "Celebration", "Get Down On It", "Joanna", "Fresh", "Cherish",
    ],
    "Bee Gees": [
        "Stayin Alive", "How Deep Is Your Love", "Night Fever", "More Than A Woman", "Tragedy",
    ],
    "ABBA": [
        "Dancing Queen", "Mamma Mia", "Take A Chance On Me", "Waterloo", "The Winner Takes It All",
        "Gimme Gimme Gimme", "Fernando", "Super Trouper",
    ],
    "Queen Latifah": [
        "U.N.I.T.Y.", "Just Another Day",
    ],
    "Lauryn Hill": [
        "Doo Wop That Thing", "Ex-Factor", "Everything Is Everything", "Can't Take My Eyes Off You",
    ],
    "OutKast": [
        "Hey Ya", "Ms Jackson", "Roses", "The Way You Move", "So Fresh So Clean",
    ],
    "50 Cent": [
        "In Da Club", "21 Questions", "Candy Shop", "Many Men", "P.I.M.P.", "If I Can't",
    ],
    "Tupac": [
        "California Love", "Changes", "Dear Mama", "Hit Em Up", "Ambitionz Az A Ridah",
        "Ghetto Gospel", "All Eyez On Me",
    ],
    "The Notorious B.I.G.": [
        "Hypnotize", "Mo Money Mo Problems", "Big Poppa", "Juicy", "One More Chance",
    ],
    "Snoop Dogg": [
        "Drop It Like It's Hot", "Gin And Juice", "Young Wild And Free", "What's My Name",
        "Beautiful", "Peaches N Cream",
    ],
    "Dr Dre": [
        "Still D.R.E.", "The Next Episode", "Forgot About Dre", "Nuthin But A G Thang",
        "California Love", "Kush",
    ],
    "Ice Cube": [
        "It Was A Good Day", "Check Yo Self", "No Vaseline", "You Know How We Do It",
    ],
    "NWA": [
        "Straight Outta Compton", "Fuck Tha Police", "Express Yourself",
    ],
    "Wu-Tang Clan": [
        "C.R.E.A.M.", "Gravel Pit", "Protect Ya Neck", "Triumph",
    ],
    "A Tribe Called Quest": [
        "Can I Kick It", "Electric Relaxation", "Scenario",
    ],
    "Nas": [
        "If I Ruled The World", "N.Y. State Of Mind", "The World Is Yours", "I Can",
    ],
    "J Cole": [
        "No Role Modelz", "Middle Child", "Power Trip", "Work Out", "Love Yourz",
    ],
    "Tyler The Creator": [
        "See You Again", "EARFQUAKE", "Yonkers", "NEW MAGIC WAND", "WUSYANAME",
    ],
    "Childish Gambino": [
        "Redbone", "This Is America", "3005", "Heartbeat", "Feels Like Summer",
    ],
    "Mac Miller": [
        "Donald Trump", "Self Care", "Weekend", "Good News", "Circles",
    ],
    "Post Malone": [
        "White Iverson", "Psycho", "Wow", "Goodbyes", "Chemical", "Candy Paint",
    ],
    "Juice WRLD": [
        "Lucid Dreams", "All Girls Are The Same", "Robbery", "Legends", "Wishing Well",
    ],
    "XXXTentacion": [
        "Sad", "Moonlight", "Changes", "Look At Me", "Jocelyn Flores",
    ],
    "Lil Uzi Vert": [
        "XO Tour Llif3", "Money Longer", "The Way Life Goes", "Just Wanna Rock",
    ],
    "Playboi Carti": [
        "Magnolia", "Shoota", "Sky", "Fein", "Location",
    ],
    "Young Thug": [
        "Die Young", "Relationship", "Hot", "Best Friend", "Go Crazy",
    ],
    "Gunna": [
        "Drip Too Hard", "fukumean", "pushin P", "DOLLAZ ON MY HEAD",
    ],
    "Lil Baby": [
        "Drip Too Hard", "The Bigger Picture", "Yes Indeed", "Freestyle", "On Me",
    ],
    "Rod Wave": [
        "Heart On Ice", "Street Runner", "By Your Side", "25",
    ],
    "Jack Harlow": [
        "First Class", "Whats Poppin", "Lovin On Me", "Tyler Herro",
    ],
    "Lil Nas X": [
        "Old Town Road", "Industry Baby", "MONTERO", "Thats What I Want",
    ],
    "Doja Cat": [
        "Say So", "Kiss Me More", "Paint The Town Red", "Woman", "Need To Know",
    ],
    "Lizzo": [
        "Truth Hurts", "Good As Hell", "About Damn Time", "Juice",
    ],
    "Halsey": [
        "Without Me", "Bad At Love", "Closer", "Gasoline", "You Should Be Sad",
    ],
    "Billie Eilish": [
        "Bad Guy", "Lovely", "Happier Than Ever", "Ocean Eyes", "Therefore I Am",
        "What Was I Made For", "Birds Of A Feather", "Bury A Friend",
    ],
    "Olivia Rodrigo": [
        "Drivers License", "Good 4 U", "Vampire", "Deja Vu", "Traitor",
    ],
    "Ariana Grande": [
        "Thank U Next", "7 rings", "Positions", "Into You", "Side To Side",
        "No Tears Left To Cry", "Break Free", "One Last Time", "Problem",
    ],
    "Selena Gomez": [
        "Come and Get It", "Lose You To Love Me", "Hands To Myself", "Same Old Love",
        "It Ain't Me", "Calm Down Remix",
    ],
    "Miley Cyrus": [
        "Flowers", "Wrecking Ball", "Party In The USA", "We Can't Stop", "Malibu",
    ],
    "Demi Lovato": [
        "Sorry Not Sorry", "Heart Attack", "Skyscraper", "Cool For The Summer",
    ],
    "Shawn Mendes": [
        "Stitches", "Treat You Better", "Senorita", "In My Blood", "There's Nothing Holdin Me Back",
    ],
    "Camila Cabello": [
        "Havana", "Never Be The Same", "Señorita", "Shameless", "Bam Bam",
    ],
    "Charlie Puth": [
        "See You Again", "Attention", "We Don't Talk Anymore", "How Long", "Left And Right",
    ],
    "James Arthur": [
        "Say You Won't Let Go", "Impossible", "Rewrite The Stars", "Car's Outside",
    ],
    "George Ezra": [
        "Budapest", "Shotgun", "Blame It On Me", "Green Green Grass",
    ],
    "Passenger": [
        "Let Her Go", "Holes", "Ride",
    ],
    "James Blunt": [
        "You're Beautiful", "Goodbye My Lover", "1973",
    ],
    "Enrique Iglesias": [
        "Bailando", "Hero", "El Perdedor", "Subeme La Radio", "Tonight",
    ],
    "Ricky Martin": [
        "Livin La Vida Loca", "She Bangs", "Maria", "Vente Pa Ca",
    ],
    "Marc Anthony": [
        "Vivir Mi Vida", "You Sang To Me", "I Need To Know",
    ],
    "Luis Fonsi": [
        "Despacito", "No Me Doy Por Vencido", "Échame La Culpa",
    ],
    "Wisin": [
        "Escapate Conmigo", "Adrenalina", "Vacaciones",
    ],
    "Yandel": [
        "Encantadora", "Explícale", "Nunca Me Olvides",
    ],
    "Farruko": [
        "Pepas", "El Incomprendido", "Chillax",
    ],
    "Feid": [
        "Chorrito Pa Las Animas", "Normal", "Ferxxo 100",
    ],
    "Peso Pluma": [
        "Ella Baila Sola", "La Bebe", "AMG", "Qlona",
    ],
    "Junior H": [
        "Disaster", "Mojado", "El Hijo Mayor",
    ],
    "Fuerza Regida": [
        "Bebe Dame", "Sabor Fresa", "TU SANCHO",
    ],
    "Grupo Frontera": [
        "No Se Va", "Bebe Dame", "Un x100to",
    ],
    "Carin Leon": [
        "Primera Cita", "Que Vuelvas", "Indispensable",
    ],
    "Christian Nodal": [
        "Adios Amor", "De Los Besos Que Te Di", "Botella Tras Botella",
    ],
    "Vicente Fernandez": [
        "Volver Volver", "Por Tu Maldito Amor", "El Rey",
    ],
    "Selena": [
        "Bidi Bidi Bom Bom", "Como La Flor", "Dreaming Of You", "Amor Prohibido",
    ],
    "Juanes": [
        "La Camisa Negra", "A Dios Le Pido", "Es Por Ti",
    ],
    "Maná": [
        "Rayando El Sol", "En El Muelle De San Blas", "Clavado En Un Bar",
    ],
    "Soda Stereo": [
        "De Musica Ligera", "Entre Canibales", "Cuando Pase El Temblor",
    ],
    "Gustavo Cerati": [
        "Crimen", "Bocanada", "Puente",
    ],
    "Caetano Veloso": [
        "Sozinho", "Terra", "Leaozinho",
    ],
    "Gilberto Gil": [
        "Aquele Abraço", "Palco", "Esperando Na Janela",
    ],
    "Jorge Ben Jor": [
        "Mas Que Nada", "Chove Chuva", "O Telefone Tocou Novamente",
    ],
    "Tim Maia": [
        "Gostava Tanto De Voce", "Descobridor Dos Sete Mares", "Não Quero Dinheiro",
    ],
    "Djavan": [
        "Oceano", "Sina", "Flor De Lis",
    ],
    "Ivete Sangalo": [
        "Sorte Grande", "Arerê", "Festa",
    ],
    "Ludmilla": [
        "Hoje", "Saudade Da Gente", "Invocada",
    ],
    "Anitta": [
        "Vai Malandra", "Meiga E Abusada", "Used To Be",
    ],
    "MC Kevin O Chris": [
        "Medo Bobo", "Tá OK", "Passagem Só Ida",
    ],
    "Matuê": [
        "Máquina do Tempo", "Cronograma", "Anos Luz",
    ],
    "Emicida": [
        "Levanta e Anda", "Passarinhos", "Habeas Corpus",
    ],
    "Racionais MCs": [
        "Diário de Um Detento", "Vida Loka", "Negro Drama",
    ],
    "Cazuza": [
        "Exagerado", "Ideologia", "O Tempo Não Para",
    ],
    "Legião Urbana": [
        "Tempo Perdido", "Pais e Filhos", "Faroeste Caboclo",
    ],
    "Titãs": [
        "Epitáfio", "Comida", "Marvin",
    ],
    "Paralamas do Sucesso": [
        "Alagados", "Caleidoscópio", "Meu Erro",
    ],
    "Engenheiros do Hawaii": [
        "Pra Ser Sincero", "Terra de Gigantes", "Dois",
    ],
    "Raimundos": [
        "Mulher de Fases", "Me Lambe", "A Mais Pedida",
    ],
    "Charlie Brown Jr": [
        "Só os Loucos Sabem", "Zoio de Lula", "Pro Dia Nascer Feliz",
    ],
    "Skank": [
        "Acima do Sol", "Sutilmente", "Garota Nacional",
    ],
    "Jota Quest": [
        "Fácil", "Doideira", "Encontrar Alguém",
    ],
    "NX Zero": [
        "Razões e Emoções", "Cedo ou Tarde", "Daqui Pra Frente",
    ],
    "CPM 22": [
        "Dias Atrás", "Um Minuto Para O Fim Do Mundo", "Regressos",
    ],
    "Pitty": [
        "Na Na Na", "Máscara", "Admirável Chip Novo",
    ],
    "Iza": [
        "Brisa", "Pesadao", "Faz Gostoso",
    ],
    "Luísa Sonza": [
        "Bomba", "Dona de Mim", "Mamacita",
    ],
    "Marília Mendonça": [
        "Infiel", "Supera", "Todo Mundo Menos Eu",
    ],
    "Henrique e Juliano": [
        "Cuida Bem Dela", "Até Você Voltar", "Arranhão",
    ],
    "Jorge e Mateus": [
        "Os Anjos Cantam", "Logo Eu", "Pode Chorar",
    ],
    "Zé Neto e Cristiano": [
        "Largado às Traças", "Notificação Preferida", "Status Que Eu Não Queria",
    ],
    "Gusttavo Lima": [
        "Balada", "Apelido Carinhoso", "Buteco In Miami",
    ],
    "Luan Santana": [
        "Meteoro", "Te Esperando", "Morena",
    ],
    "Michel Teló": [
        "Ai Se Eu Te Pego", "Bara Bara Bere Bere", "Fugidinha",
    ],
    "Israel Kamakawiwoole": [
        "Somewhere Over The Rainbow", "White Sandy Beach",
    ],
    "Bob Dylan": [
        "Like A Rolling Stone", "Blowin In The Wind", "Knockin On Heaven's Door",
        "The Times They Are A-Changin", "Hurricane",
    ],
    "Neil Young": [
        "Heart Of Gold", "Old Man", "Harvest Moon", "Rockin In The Free World",
    ],
    "Joni Mitchell": [
        "Big Yellow Taxi", "Both Sides Now", "A Case Of You", "River",
    ],
    "Leonard Cohen": [
        "Hallelujah", "Suzanne", "So Long Marianne",
    ],
    "Simon and Garfunkel": [
        "The Sound Of Silence", "Bridge Over Troubled Water", "Mrs Robinson", "Cecilia",
    ],
    "The Beach Boys": [
        "Good Vibrations", "God Only Knows", "Wouldn't It Be Nice", "Surfin USA",
    ],
    "The Doors": [
        "Light My Fire", "Riders On The Storm", "Break On Through", "People Are Strange",
    ],
    "Jimi Hendrix": [
        "Purple Haze", "All Along The Watchtower", "Voodoo Child", "Hey Joe",
    ],
    "The Who": [
        "Baba O Riley", "My Generation", "Behind Blue Eyes", "Pinball Wizard",
    ],
    "Cream": [
        "Sunshine Of Your Love", "White Room", "Crossroads",
    ],
    "The Jimi Hendrix Experience": [
        "Foxy Lady", "Little Wing",
    ],
    "Deep Purple": [
        "Smoke On The Water", "Highway Star", "Child In Time",
    ],
    "Black Sabbath": [
        "Paranoid", "Iron Man", "War Pigs", "N.I.B.",
    ],
    "Iron Maiden": [
        "Run To The Hills", "The Trooper", "Fear Of The Dark", "Number Of The Beast",
    ],
    "Judas Priest": [
        "Breaking The Law", "Living After Midnight", "Painkiller",
    ],
    "Ozzy Osbourne": [
        "Crazy Train", "Mama I'm Coming Home", "No More Tears", "Mr Crowley",
    ],
    "Def Leppard": [
        "Pour Some Sugar On Me", "Love Bites", "Photograph", "Hysteria",
    ],
    "Bon Jovi": [
        "Livin On A Prayer", "You Give Love A Bad Name", "It's My Life", "Always",
        "Wanted Dead Or Alive", "Bed Of Roses",
    ],
    "Aerosmith": [
        "I Don't Want To Miss A Thing", "Dream On", "Sweet Emotion", "Walk This Way",
        "Crazy", "Janie's Got A Gun",
    ],
    "Guns N' Roses": [
        "Sweet Child O Mine", "November Rain", "Welcome To The Jungle",
    ],
    "Scorpions": [
        "Wind Of Change", "Still Loving You", "Rock You Like A Hurricane",
    ],
    "Rammstein": [
        "Du Hast", "Sonne", "Deutschland", "Engel",
    ],
    "System Of A Down": [
        "Chop Suey", "Toxicity", "B.Y.O.B.", "Aerials",
    ],
    "Slipknot": [
        "Duality", "Before I Forget", "Wait And Bleed", "Psychosocial",
    ],
    "Korn": [
        "Freak On A Leash", "Coming Undone", "Falling Away From Me",
    ],
    "Limp Bizkit": [
        "Rollin", "Nookie", "Break Stuff", "My Way",
    ],
    "Blink-182": [
        "All The Small Things", "What's My Age Again", "I Miss You", "Adam's Song",
    ],
    "Sum 41": [
        "In Too Deep", "Fat Lip", "Still Waiting", "Pieces",
    ],
    "The Offspring": [
        "Pretty Fly", "Self Esteem", "Why Don't You Get A Job", "The Kids Aren't Alright",
    ],
    "Rancid": [
        "Time Bomb", "Ruby Soho", "Fall Back Down",
    ],
    "Arctic Monkeys": [
        "Do I Wanna Know", "R U Mine", "505", "I Bet You Look Good On The Dancefloor",
        "Fluorescent Adolescent", "Why'd You Only Call Me When You're High",
    ],
    "The Strokes": [
        "Last Nite", "Reptilia", "You Only Live Once", "Hard To Explain",
    ],
    "The Killers": [
        "Mr Brightside", "Somebody Told Me", "When You Were Young", "Human",
        "All These Things That I've Done", "Read My Mind",
    ],
    "Muse": [
        "Starlight", "Supermassive Black Hole", "Uprising", "Knights Of Cydonia",
        "Hysteria", "Time Is Running Out",
    ],
    "Oasis": [
        "Wonderwall", "Don't Look Back In Anger", "Champagne Supernova", "Live Forever",
        "Supersonic", "Stop Crying Your Heart Out",
    ],
    "Blur": [
        "Song 2", "Girls And Boys", "Parklife", "Coffee And TV",
    ],
    "Pulp": [
        "Common People", "Disco 2000", "Babies",
    ],
    "The Cure": [
        "Friday I'm In Love", "Just Like Heaven", "Boys Don't Cry", "Lovesong",
        "Pictures Of You", "Close To Me",
    ],
    "Depeche Mode": [
        "Enjoy The Silence", "Personal Jesus", "Just Can't Get Enough", "Policy Of Truth",
    ],
    "New Order": [
        "Blue Monday", "Regret", "True Faith",
    ],
    "Joy Division": [
        "Love Will Tear Us Apart", "She's Lost Control", "Disorder",
    ],
    "Talking Heads": [
        "Psycho Killer", "Burning Down The House", "Once In A Lifetime", "This Must Be The Place",
    ],
    "The Police": [
        "Every Breath You Take", "Roxanne", "Message In A Bottle", "Don't Stand So Close To Me",
    ],
    "Dire Straits": [
        "Sultans Of Swing", "Money For Nothing", "Brothers In Arms", "Walk Of Life",
    ],
    "Phil Collins": [
        "In The Air Tonight", "Another Day In Paradise", "Against All Odds", "One More Night",
    ],
    "Genesis": [
        "Invisible Touch", "That's All", "Land Of Confusion", "Follow You Follow Me",
    ],
    "Peter Gabriel": [
        "Sledgehammer", "In Your Eyes", "Solsbury Hill",
    ],
    "Billy Joel": [
        "Piano Man", "Uptown Girl", "Just The Way You Are", "We Didn't Start The Fire",
        "Vienna", "She's Always A Woman",
    ],
    "Bruce Springsteen": [
        "Born To Run", "Dancing In The Dark", "Streets Of Philadelphia", "Thunder Road",
        "Hungry Heart", "Glory Days",
    ],
    "Tom Petty": [
        "Free Fallin", "I Won't Back Down", "American Girl", "Learning To Fly",
    ],
    "John Mellencamp": [
        "Jack and Diane", "Small Town", "Hurts So Good",
    ],
    "Fleet Foxes": [
        "White Winter Hymnal", "Mykonos", "Helplessness Blues",
    ],
    "Bon Iver": [
        "Skinny Love", "Holocene", "For Emma", "Can't Enforce",
    ],
    "Sufjan Stevens": [
        "Chicago", "Mystery Of Love", "Death With Dignity",
    ],
    "The National": [
        "I Need My Girl", "Bloodbuzz Ohio", "Fake Empire",
    ],
    "Arcade Fire": [
        "Wake Up", "The Suburbs", "Ready To Start", "Sprawl II",
    ],
    "Vampire Weekend": [
        "A-Punk", "Harmony Hall", "Cape Cod Kwassa Kwassa",
    ],
    "Tame Impala": [
        "The Less I Know The Better", "Let It Happen", "Feels Like We Only Go Backwards",
        "Elephant", "Eventually",
    ],
    "Glass Animals": [
        "Heat Waves", "Gooey", "Toes", "Life Itself",
    ],
    "Foster The People": [
        "Pumped Up Kicks", "Sit Next to Me", "Houdini",
    ],
    "MGMT": [
        "Kids", "Electric Feel", "Time To Pretend", "When You Die",
    ],
    "Phoenix": [
        "1901", "Lisztomania", "If I Ever Feel Better",
    ],
    "Two Door Cinema Club": [
        "What You Know", "Something Good Can Work", "Undercover Martyn",
    ],
    "The 1975": [
        "Chocolate", "Somebody Else", "Love It If We Made It", "Robbers",
    ],
    "Arctic Monkeys": [
        "Arabella", "Snap Out Of It", "Tranquility Base Hotel and Casino",
    ],
    "Lana Del Rey": [
        "Summertime Sadness", "Video Games", "Young And Beautiful", "West Coast",
        "Born To Die", "Doin Time",
    ],
    "Florence and The Machine": [
        "Dog Days Are Over", "Shake It Out", "You've Got The Love", "Ship To Wreck",
    ],
    "Adele": [
        "Water Under The Bridge", "Chasing Pavements", "Make You Feel My Love",
    ],
    "Amy Winehouse": [
        "Rehab", "Back To Black", "You Know I'm No Good", "Valerie", "Tears Dry On Their Own",
    ],
    "Duffy": [
        "Mercy", "Warwick Avenue", "Stepping Stone",
    ],
    "Corinne Bailey Rae": [
        "Put Your Records On", "Like A Star", "Trouble Sleeping",
    ],
    "John Mayer": [
        "Slow Dancing In A Burning Room", "Gravity", "Your Body Is A Wonderland", "Daughters",
    ],
    "Ed Sheeran": [
        "The A Team", "Sing", "Shivers", "Shape Of You acoustic",
    ],
    "James Bay": [
        "Hold Back The River", "Let It Go", "Us",
    ],
    "Vance Joy": [
        "Riptide", "Georgia", "Fire and the Flood",
    ],
    "Lorde": [
        "Royals", "Green Light", "Team", "Solar Power", "Liability",
    ],
    "Tove Lo": [
        "Habits Stay High", "Talking Body", "Disco Tits",
    ],
    "Zara Larsson": [
        "Lush Life", "Never Forget You", "Symphony",
    ],
    "Clean Bandit": [
        "Rather Be", "Rockabye", "Symphony", "Solo",
    ],
    "Rudimental": [
        "Waiting All Night", "Feel The Love", "These Days",
    ],
    "Disclosure": [
        "Latch", "When A Fire Starts To Burn", "White Noise", "You and Me",
    ],
    "Flume": [
        "Never Be Like You", "Say It", "Holdin On",
    ],
    "Kygo": [
        "Firestone", "Stole The Show", "It Ain't Me", "Higher Love",
    ],
    "Zedd": [
        "Clarity", "Stay", "The Middle", "Beautiful Now",
    ],
    "Alesso": [
        "Heroes", "If I Lose Myself", "Take My Breath Away",
    ],
    "Afrojack": [
        "Take Over Control", "Turn Up The Speakers", "Give Me Everything",
    ],
    "Major Lazer": [
        "Lean On", "Cold Water", "Light It Up", "Watch Out For This",
    ],
    "DJ Snake": [
        "Turn Down For What", "Let Me Love You", "Taki Taki", "Middle",
    ],
    "Pitbull": [
        "Give Me Everything", "Timber", "International Love", "Hotel Room Service",
        "I Know You Want Me", "Fireball",
    ],
    "Flo Rida": [
        "Low", "Good Feeling", "Club Can't Handle Me", "My House", "Whistle",
    ],
    "LMFAO": [
        "Party Rock Anthem", "Sexy And I Know It", "Sorry For Party Rocking",
    ],
    "Black Eyed Peas": [
        "I Gotta Feeling", "Pump It", "Where Is The Love", "Boom Boom Pow", "Meet Me Halfway",
    ],
    "will.i.am": [
        "Scream and Shout", "This Is Love", "Bang Bang",
    ],
    "Fergie": [
        "Big Girls Don't Cry", "Fergalicious", "Glamorous", "London Bridge",
    ],
    "Nelly Furtado": [
        "Promiscuous", "Say It Right", "I'm Like A Bird", "Maneater",
    ],
    "Shaggy": [
        "It Wasn't Me", "Angel", "Boombastic", "Wasn't Me",
    ],
    "Sean Paul": [
        "Temperature", "Get Busy", "We Be Burnin", "Give It Up To Me",
    ],
    "Damian Marley": [
        "Welcome To Jamrock", "Road To Zion", "Medication",
    ],
    "Sean Kingston": [
        "Beautiful Girls", "Fire Burning", "Take You There",
    ],
    "Jason Derulo": [
        "Talk Dirty", "Want To Want Me", "Whatcha Say", "Ridin Solo",
    ],
    "Ne-Yo": [
        "So Sick", "Miss Independent", "Closer", "Because Of You",
    ],
    "Chris Brown": [
        "With You", "Forever", "Run It", "No Guidance", "Under The Influence",
    ],
    "T-Pain": [
        "Buy U A Drank", "Bartender", "Can't Believe It", "Up Down",
    ],
    "Ludacris": [
        "Money Maker", "What's Your Fantasy", "Act A Fool", "Move Bitch",
    ],
    "M.I.A.": [
        "Paper Planes", "Bad Girls", "Galang",
    ],
    "Gorillaz": [
        "Feel Good Inc", "Clint Eastwood", "On Melancholy Hill", "DARE", "New Gold",
    ],
    "Massive Attack": [
        "Teardrop", "Unfinished Sympathy", "Paradise Circus",
    ],
    "Portishead": [
        "Glory Box", "Sour Times", "Only You",
    ],
    "Bjork": [
        "Army Of Me", "Hyperballad", "It's Oh So Quiet", "Bachelorette",
    ],
    "Enya": [
        "Orinoco Flow", "Only Time", "May It Be",
    ],
    "Celine Dion": [
        "Because You Loved Me live", "Pour que tu m'aimes encore",
    ],
    "Andrea Bocelli": [
        "Con Te Partirò", "Time To Say Goodbye", "Vivo Per Lei",
    ],
    "Luciano Pavarotti": [
        "Nessun Dorma", "O Sole Mio",
    ],
    "Stromae": [
        "Papaoutai", "Alors On Danse", "Formidable", "Tous Les Mêmes", "Carmen",
    ],
    "Indila": [
        "Dernière Danse", "Tourner Dans Le Vide", "Love Story",
    ],
    "Zaz": [
        "Je Veux", "On Ira", "Si", "Sympathique",
    ],
    "Christophe Mae": [
        "Belle Demoiselle Hotel", "On S'attache", "Mon Pays",
    ],
    "Maître Gims": [
        "Sapés comme jamais", "Est-ce que tu m'aimes", "Bella",
    ],
    "Orelsan": [
        "Basique", "La fête est finie", "Jour meilleur",
    ],
    "Damso": [
        "Macarena", "Θ. Macarena", "Ipseite",
    ],
    "Jul": [
        "La bandite", "Tchikita", "La zone",
    ],
    "Ninho": [
        "M.I.L.S", "Jefe", "Goutte d'eau",
    ],
    "Booba": [
        "DKR", "Validée", "PGP",
    ],
    "SCH": [
        "Jodio Gang", "Génération Assassin", "Mode Akimbo",
    ],
    "PNL": [
        "Au DD", "Naha", "Le monde ou rien", "J'suis QLF",
    ],
    "Angèle": [
        "Tout oublier", "Balance ton quoi", "Flou", "Bruxelles je t'aime",
    ],
    "Renaud": [
        "Mistral Gagnant", "Laisse béton", "Dès que le vent soufflera",
    ],
    "Charles Aznavour": [
        "La Bohème", "For me formidable", "Hier encore",
    ],
    "Edith Piaf": [
        "La Vie En Rose", "Non je ne regrette rien", "Milord",
    ],
    "Måneskin": [
        "Beggin", "I Wanna Be Your Slave", "Gossip", "The Loneliest",
    ],
    "Laura Pausini": [
        "La solitudine", "Strani amori", "Vivimi",
    ],
    "Eros Ramazzotti": [
        "Più bella cosa", "Un attimo di te", "Cose della vita",
    ],
    "Tiziano Ferro": [
        "Perdono", "Sere nere", "Tardes negras",
    ],
    "Jovanotti": [
        "Penso positivo", "Serenata", "L'ombelico del mondo",
    ],
    "Vasco Rossi": [
        "Albachiara", "Sally", "Vita spericolata",
    ],
    "Ligabue": [
        "Certe notti", "M'abituerò", "Balliamo sul mondo",
    ],
    "Zucchero": [
        "Baila morena", "Senza una donna", "Il bastardo",
    ],
    "Andrea Bocelli": [
        "Vivo per lei", "Romanza",
    ],
    "Raphael": [
        "Yo soy aquel", "Escándalo", "Mi gran noche",
    ],
    "Rocío Dúrcal": [
        "Amor eterno", "Diferente", "La gata bajo la lluvia",
    ],
    "Alejandro Sanz": [
        "Corazón partío", "No es lo mismo", "Desde cuando",
    ],
    "Melendi": [
        "Caminando por la vida", "Tu jardín con enanitos", "Un violinista en tu tejado",
    ],
    "Estopa": [
        "La raja de tu falda", "Vino tinto", "Como camarn",
    ],
    "Jarabe de Palo": [
        "La flaca", "Depende", "Bonito",
    ],
    "Héroes del Silencio": [
        "Entre dos tierras", "Maldito duende", "Avalancha",
    ],
    "Mecano": [
        "Hijo de la luna", "Me cuesta tanto olvidarte", "La fuerza del destino",
    ],
    "Raphael": [
        "Escándalo",
    ],
}
