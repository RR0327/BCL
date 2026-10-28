import json
import sys
from pathlib import Path

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

# Passages
p1_text = """The game of tennis has a very long history. It is officially still known as “lawn tennis,” partly because it was originally only played on grass, and also to distinguish it from the older game known as “real tennis,” from which the modern game developed.

Some people believe that the ancient Egyptians, Greeks, and Romans played various versions of tennis. No drawings or descriptions of any tennis-like games have been discovered, but a couple of Arabic words dating from ancient Egyptian times are cited as evidence. The theory goes that the name “tennis” is derived from the Egyptian town of Tennis alongside the Nile, and the word “racquet” evolved from the Arabic word for the palm of the hand, rahat.

Aside from these two Arabic words, there is no other evidence for any form of tennis prior to the year 1000. Most historians believe the origins of the game date back to 11th- and 12th-century France. It’s thought that French monks were the first to play a basic game of handball against their monastery buildings, or over a rope strung across a courtyard. Those who dispute more ancient origins argue that the name “tennis” is derived from the French tenez, which meant something to the effect of “take this,” said as one player would serve to the other.

This game took on the name jeu de paume, which means “game of the hand or palm.” But as they found playing with bare hands quite uncomfortable, players began using a simple glove, and later either a glove with webbing between the fingers or a solid paddle, similar to the ones used in table tennis today. Wooden racquets were not invented until much later.

The French nobility learned the game from the monks, and some accounts report as many as 1,800 tennis courts in France by the 13th century. The game, which remained exclusive to the upper classes, gained more popularity over the 14th and 15th centuries. As it became increasingly fashionable, outdoor courtyards were modified into indoor courts. The game became such a widespread diversion among the aristocracy that both the pope and the French king tried to ban it. By the 16th century, the game had spread to England, where it became known as “tennis.” Both kings Henry VII and Henry VIII were avid players who promoted the building of courts, and it also became a very fashionable game among the English upper classes.

An example of one of these early “real tennis” courts can be seen at the royal palace of Hampton Court near London. It was built in 1525 and is still used today. Only a handful of such courts remain. It is a tall, narrow indoor court, bearing more resemblance to a squash court than the type of tennis courts we are familiar with today. “Real tennis” is a remarkably fast and difficult game as the ball can be bounced off any of the surfaces, some of which are slanted at odd angles. The net is just over 1.5 metres high at each end, but drops to just under a metre in the middle.

Until the 19th century, the ball was either constructed from a wad of hair, wool, or cork wrapped in string and cloth or leather. Then a major development took place when Charles Goodyear invented vulcanisation, a process that allows rubber to withstand heat and cold. This led to the development of rubber tennis balls. During the 1850s, players began to experiment with these new balls, which bounced easily on outdoor grass courts.

In 1874 a Welshman, Major Walter C. Wingfield, known as “the father of lawn tennis,” had the idea of devising rules, which he published. He also introduced standardised equipment, including racquets, balls, posts, and a net, which he patented and sold in sets. The game quickly became a very popular and sociable open-air pursuit for the English middle classes. People also started playing tennis in countries such as the United States, Russia, India, Canada, and China. However, not all of Wingfield’s ideas ultimately survived. Inspired by his knowledge of Greek, he called his version of tennis Sphairistike - a name which never caught on. Interestingly, his original court had the shape of an hourglass, with the net across its narrowest section.

A major tennis tournament took place for the first time in Wimbledon, London in 1877, and its organising committee came up with a rectangular court and a modified set of rules that are essentially the same as for the game we know today. The net was still high at the sides, a carryover from the game’s indoor ancestor. But by 1882, the specifications for the size of the court, the equipment, and the rules had evolved to their current form."""

p2_text = """14 The 17th-century English scholar and botanist John Ray was well aware that he lived through, and participated in, a profound revolution in the way people interacted with nature. In the preface to his Synopsis of British Plants, published in 1690, he gave thanks that he had been born at a time when traditional dependence on the teaching of the Greek philosopher Aristotle (384-322 BCE) had given way to a new philosophy, based on experiment and observation of the real world, that we now call science.

15 Ray was born in 1627. His father was a village blacksmith, and his mother was also a respected member of the community, a healer who was an expert in folk medicine and the use of herbs to treat ailments. Ray must have stood out as an unusually bright boy among his schoolmates, and his talents were recognised by a church official, Samuel Covell, who had graduated from Cambridge University in 1600, and maintained his links with his university. Through his influence, Ray was admitted to Cambridge University in 1644 at the age of seventeen - a huge step for a village blacksmith’s son. There he made a solid start, and quickly gained a reputation as a brilliant student. He studied the classics (Greek, Latin and Hebrew) and mathematics, but there was nothing yet we would now call science in the curriculum. After graduating in 1648, he became a minor member of staff at Trinity College, Cambridge. He was appointed Lecturer in Greek in 1651, Lecturer in Mathematics in 1653, and Lecturer in Humanities in 1655.

16 Almost immediately after graduating, Ray also seems to have developed the interest to which he would devote the rest of his life: the study of the natural world. He explains this conversion into a naturalist - in particular into a botanist - in the preface to his first book, the Cambridge Catalogue of English Plants. Here Ray tells us that he suffered an illness in his early twenties, and was advised to take long walks and ride in the fresh air while recovering. While doing this, he became interested in the local flora, and finding nobody able to teach him, Ray investigated it for himself. He then went on to pass on the knowledge he acquired to others.

17 By the mid-1650s, even the first-year students at Trinity College were able to identify the plants and flowers around Cambridge, as they were being taught (unofficially - none of this was part of their formal education) by Ray. Many of them were the sons of landowners, and so had a natural, if amateurish, interest in country matters. But a few of them took his efforts to understand the natural world much more seriously. One of these, Francis Willughby, later played an important part in Ray’s life.

18 Having himself had no authority on the subject of plants on which to draw, Ray also started work on what would become his Cambridge Catalogue of English Plants. The work was not published until 1660 because, as Ray explained in the preface, he had to start from scratch: “I had first to become familiar with the literature, to compare the plants that I found with the pictures, and when there seemed to be a resemblance, to go fully into any unknown descriptions. Gaining skill by experience, I acquired at last the ability to recognise to what tribe and family similars could be assigned; this taught me to search for similarities and saved a vast deal of labour, which others would have spent in their difficulties. I was eager to make the most of this and was fortunate to share my enthusiasm with my friends …”

19 Ray’s Cambridge Catalogue of English Plants was much more than a simple list of species. It gave the names of plants found in the area around Cambridge and included information about where they grew and how common they were. In doing this, Ray was producing something that would be of practical use to students and other readers interested in the local natural world. At the same time, the book showed his determination to describe plants accurately, on the basis of direct examination rather than reliance on old authorities. In this respect, it reflected the spirit of the new learning that Ray admired.

20 Ray’s studies of plants were only the beginning of a much larger ambition. With the support of Francis Willughby, he began to imagine a more comprehensive investigation of nature, one that would attempt to classify living things according to careful observation of their shared characteristics. This was an ambitious undertaking, especially at a time when many aspects of the natural world remained poorly described. Yet Ray believed that by collecting evidence systematically and comparing related forms, it would be possible to build a more reliable understanding of nature than scholars had possessed before."""

p3_text = """A Francis Ronalds was born in London in 1788, the second of eleven children. When he was nineteen his father died, and as the eldest son, the young Ronalds had to assume the responsibility of running the family’s cheese business. He combined this occupation with his passions for chemical experiments and for meteorology, the study of the Earth’s atmosphere and its changes. This brought him into contact with the elderly Swiss meteorologist Jean Andre de Luc, who was also an inspired inventor in the field of electricity. In 1814, de Luc encouraged Ronalds to start work on this new discipline.

B For the next few years, Ronalds experimented enthusiastically with various kinds of electrostatic clockwork devices. He was particularly interested in the idea of electric telegraphy: transmitting messages over distance, using electrical impulses carried along metal wires. In the best traditions of nineteenth-century scientists, these investigations were carried out at home. In early 1816, Ronalds gutted the family home in Hammersmith, West London, and covered its rooms, halls, and staircases with electric wire. This experiment involved the use of current to produce movement in small corks at the ends of circuits.

C Some months later, Ronalds built two large wooden frames accommodating 8 miles (12.9 km) of electrically charged iron wire in his back garden. At either end of the wire was a revolving disc, on which letters and numbers were engraved. These dials were kept revolving by means of a clockwork mechanism. When somebody wanted to send a message, he would wait until the dial at his end was showing the desired number or letter, and then interrupt the charge on the wire. This would cause two balls suspended on the wire to fall together. The person at the opposite end would then note down what was indicated by the dial at his end at the moment when the balls made contact. Ronalds soon developed a modified version of his invention in which the wire was encased in glass tubes and buried in the ground. The system was slow and depended on the two dials staying in step, but it worked.

D Ronalds immediately contacted the Admiralty, the department of the British government which had control over the nation’s naval affairs. He was not the first to propose a system of this nature to them. Some ten years earlier, in 1806, the inventor Ralph Wedgwood had offered the Admiralty a similar type of telegraph based on frictional electricity, which it had rejected. The Admiralty had its home in London, whereas its naval fleets were based over 130 km away in Portsmouth. With communication between these two cities in mind, Ronalds wrote to Lord Melville, the then First Lord of the Admiralty, to offer him his telegraphic system.

E Ronalds believed that his invention was capable of carrying messages some 800 km, and in his letter to Lord Melville written on 11 July 1816 he spoke of the “mode of conveying telegraphic intelligence with great rapidity, accuracy, and certainty, in all states of the atmosphere, either at night or in the day, and at small expense.” In 1816, the Admiralty had at its disposal only the late eighteenth-century telegraphic system of semaphore, whereby a mechanical device was used to control a mast with two arms. The disadvantage of this system was that it was only usable in daylight and in clear weather conditions. Nevertheless, John Barrow, Secretary to the Admiralty, wrote back to Ronalds on 5 August, saying that “telegraphs of any kind are wholly unnecessary, and NO other than the one now in use will be adopted.”

F Ronalds did not pursue the matter further or attempt to patent his telegraph. However, in a small pamphlet published in 1823, he described his invention and listed some of its potential uses. Although Ronalds lived long enough to see his prophecies come to fruition, he made no further contribution to the progress of telegraphic communication. In 1843, he was appointed the first Honorary Director and Superintendent of the Observatory at Kew, where he devised an accurate, automatic system for registering meteorological data using photography. A similar system was developed independently by Charles Brooke, but the British Association of Meteorologists confirmed Ronalds’s priority. His system remained in use for many decades.

G Meanwhile, the people who benefited most directly from Ronalds’s telegraphic work were the physicist Charles Wheatstone and his business partner William Cooke. They saw the potential of a rapid communication system for the growing number of private railway companies, and in 1837 they developed the Wheatstone-Cooke five-needle telegraph. The pair patented their design in the same year, the first of its kind to be officially registered, and reaped considerable financial gain as a result. Ronalds himself retired in 1852 and devoted his later years to collecting and cataloguing a vast library of published material on electricity and magnetism. In 1870, three years before he died, he was knighted by Queen Victoria, a belated honour in recognition of his “early and remarkable labours in telegraphic investigations.”"""

def get_tfng_options(correct):
    return [
        {"option_key": "TRUE", "option_text": "TRUE", "is_correct": correct == "TRUE"},
        {"option_key": "FALSE", "option_text": "FALSE", "is_correct": correct == "FALSE"},
        {"option_key": "NOT GIVEN", "option_text": "NOT GIVEN", "is_correct": correct == "NOT GIVEN"}
    ]

# Headings for Passage 2
headings_p2 = [
    ("i", "Ray’s account of his working methods"),
    ("ii", "The botanical expert who inspired Ray"),
    ("iii", "A succession of academic achievements"),
    ("iv", "Ray’s informal tuition"),
    ("v", "Ray’s appreciation of his contemporary academic culture"),
    ("vi", "A childhood interest in plants"),
    ("vii", "Plans for a bold new project"),
    ("viii", "A description of the content of Ray’s first book"),
    ("ix", "A change of direction for Ray")
]

def get_headings_options(correct):
    return [
        {"option_key": k, "option_text": t, "is_correct": k == correct}
        for k, t in headings_p2
    ]

# Choose TWO options for Q25 & Q26
choose_two_options_raw = [
    ("A", "His teacher recommended that he should go to university."),
    ("B", "His school record was not exceptional in any way."),
    ("C", "He was helped by a former student of Cambridge University."),
    ("D", "His parents were both valued by the people in their local area."),
    ("E", "He originally planned to take up his father’s occupation.")
]

def get_choose_two_options(correct):
    return [
        {"option_key": k, "option_text": t, "is_correct": k == correct}
        for k, t in choose_two_options_raw
    ]

# Matching Dates for Q27-Q31
dates_raw = [
    ("A", "1806"),
    ("B", "1814"),
    ("C", "1816"),
    ("D", "1823"),
    ("E", "1837"),
    ("F", "1843"),
    ("G", "1852"),
    ("H", "1870")
]

def get_dates_options(correct):
    return [
        {"option_key": k, "option_text": t, "is_correct": k == correct}
        for k, t in dates_raw
    ]

# Matching Paragraphs A-G for Q36-Q40
paras_raw = [
    ("A", "Paragraph A"),
    ("B", "Paragraph B"),
    ("C", "Paragraph C"),
    ("D", "Paragraph D"),
    ("E", "Paragraph E"),
    ("F", "Paragraph F"),
    ("G", "Paragraph G")
]

def get_paras_options(correct):
    return [
        {"option_key": k, "option_text": t, "is_correct": k == correct}
        for k, t in paras_raw
    ]

# Section 1 Questions
s1_questions = [
    {
        "order": 1,
        "question_type": "tfng",
        "question_instructions": "Do the following statements agree with the information given in Reading Passage 1? In boxes 1–6 on your answer sheet, choose TRUE if the statement agrees with the information, FALSE if the statement contradicts the information, or NOT GIVEN if there is no information on this.",
        "question_text": "There are a few surviving documents which show that a game similar to tennis was played in the ancient world.",
        "correct_answer": "FALSE",
        "answer_location": "Paragraph 2",
        "passage_excerpt": "No drawings or descriptions of any tennis-like games have been discovered, but a couple of Arabic words dating from ancient Egyptian times are cited as evidence.",
        "what_question_asks": "The statement claims that there are surviving historical documents showing that a game resembling tennis was played in ancient civilizations.",
        "what_passage_says": "The passage explicitly notes that 'No drawings or descriptions of any tennis-like games have been discovered', with only two Arabic words cited as theoretical evidence.",
        "why_answer": "Because the text clearly states that no drawings or descriptions (documents) have ever been found, the statement directly contradicts the passage. The answer is FALSE.",
        "paraphrase": "surviving documents which show that a game similar to tennis was played -> drawings or descriptions of any tennis-like games have been discovered",
        "tip": "'No drawings or descriptions' directly contradicts 'a few surviving documents'.",
        "options": get_tfng_options("FALSE")
    },
    {
        "order": 2,
        "question_type": "tfng",
        "question_instructions": "Do the following statements agree with the information given in Reading Passage 1? In boxes 1–6 on your answer sheet, choose TRUE if the statement agrees with the information, FALSE if the statement contradicts the information, or NOT GIVEN if there is no information on this.",
        "question_text": "An early form of tennis involved players hitting a ball with just their hand.",
        "correct_answer": "TRUE",
        "answer_location": "Paragraph 3",
        "passage_excerpt": "It’s thought that French monks were the first to play a basic game of handball against their monastery buildings, or over a rope strung across a courtyard.",
        "what_question_asks": "Whether an early version of the sport was played by striking the ball directly with the bare hand.",
        "what_passage_says": "The passage explains that French monks initially played 'a basic game of handball' called 'jeu de paume' ('game of the hand or palm') and that players originally played with 'bare hands'.",
        "why_answer": "The text confirms that early players struck the ball with just their bare hands before developing gloves and paddles. The statement is TRUE.",
        "paraphrase": "hitting a ball with just their hand -> basic game of handball ... jeu de paume ('game of the hand or palm') ... playing with bare hands",
        "tip": "'Handball' and 'playing with bare hands' confirm the statement directly.",
        "options": get_tfng_options("TRUE")
    },
    {
        "order": 3,
        "question_type": "tfng",
        "question_instructions": "Do the following statements agree with the information given in Reading Passage 1? In boxes 1–6 on your answer sheet, choose TRUE if the statement agrees with the information, FALSE if the statement contradicts the information, or NOT GIVEN if there is no information on this.",
        "question_text": "The game of table tennis developed around the same time as tennis.",
        "correct_answer": "NOT GIVEN",
        "answer_location": "Paragraph 4",
        "passage_excerpt": "and later either a glove with webbing between the fingers or a solid paddle, similar to the ones used in table tennis today.",
        "what_question_asks": "Whether table tennis originated around the same historical era as early tennis.",
        "what_passage_says": "Table tennis is mentioned solely to compare its modern paddle to early solid paddles ('similar to the ones used in table tennis today').",
        "why_answer": "The text provides no information about when table tennis itself was invented or developed. Therefore, the statement is NOT GIVEN.",
        "paraphrase": "No chronological information about table tennis's development is provided in the passage.",
        "tip": "Comparing modern equipment to historical gear does not give information about the origin date of the modern sport.",
        "options": get_tfng_options("NOT GIVEN")
    },
    {
        "order": 4,
        "question_type": "tfng",
        "question_instructions": "Do the following statements agree with the information given in Reading Passage 1? In boxes 1–6 on your answer sheet, choose TRUE if the statement agrees with the information, FALSE if the statement contradicts the information, or NOT GIVEN if there is no information on this.",
        "question_text": "Tennis became popular with all sections of French society in the 14th and 15th centuries.",
        "correct_answer": "FALSE",
        "answer_location": "Paragraph 5",
        "passage_excerpt": "The game, which remained exclusive to the upper classes, gained more popularity over the 14th and 15th centuries.",
        "what_question_asks": "Whether tennis was embraced by every social class across French society during the 14th and 15th centuries.",
        "what_passage_says": "Paragraph 5 states that while the game gained popularity, it 'remained exclusive to the upper classes'.",
        "why_answer": "The game was restricted exclusively to the nobility/upper classes, directly contradicting the claim that it was popular with 'all sections of French society'. The answer is FALSE.",
        "paraphrase": "all sections of French society -> exclusive to the upper classes",
        "tip": "Watch for absolute quantifiers like 'all sections', which often contradict restrictive text like 'exclusive to'.",
        "options": get_tfng_options("FALSE")
    },
    {
        "order": 5,
        "question_type": "tfng",
        "question_instructions": "Do the following statements agree with the information given in Reading Passage 1? In boxes 1–6 on your answer sheet, choose TRUE if the statement agrees with the information, FALSE if the statement contradicts the information, or NOT GIVEN if there is no information on this.",
        "question_text": "The indoor courts created in the 14th and 15th centuries were larger than the outdoor courtyards.",
        "correct_answer": "NOT GIVEN",
        "answer_location": "Paragraph 5",
        "passage_excerpt": "As it became increasingly fashionable, outdoor courtyards were modified into indoor courts.",
        "what_question_asks": "Whether the indoor courts built in the 14th and 15th centuries were greater in physical size than the earlier outdoor courtyards.",
        "what_passage_says": "The text only notes that 'outdoor courtyards were modified into indoor courts' as the sport became fashionable.",
        "why_answer": "There is no comparative information about the relative dimensions or surface area of indoor courts versus outdoor courtyards. Thus, the statement is NOT GIVEN.",
        "paraphrase": "No size comparison exists between the outdoor and indoor playing areas in the text.",
        "tip": "Modification of a space does not indicate whether the new space was larger or smaller.",
        "options": get_tfng_options("NOT GIVEN")
    },
    {
        "order": 6,
        "question_type": "tfng",
        "question_instructions": "Do the following statements agree with the information given in Reading Passage 1? In boxes 1–6 on your answer sheet, choose TRUE if the statement agrees with the information, FALSE if the statement contradicts the information, or NOT GIVEN if there is no information on this.",
        "question_text": "There were attempts to prevent French aristocrats from playing tennis.",
        "correct_answer": "TRUE",
        "answer_location": "Paragraph 5",
        "passage_excerpt": "The game became such a widespread diversion among the aristocracy that both the pope and the French king tried to ban it.",
        "what_question_asks": "Whether ruling authorities tried to stop French noblemen from playing tennis.",
        "what_passage_says": "Because the game was such a diversion among the aristocracy, 'both the pope and the French king tried to ban it'.",
        "why_answer": "Both the French king and the pope attempted to outlaw the game among the aristocracy, meaning there were indeed official attempts to stop them from playing. The statement is TRUE.",
        "paraphrase": "attempts to prevent ... from playing -> both the pope and the French king tried to ban it",
        "tip": "'Tried to ban it' is a direct synonym for 'attempts to prevent from playing'.",
        "options": get_tfng_options("TRUE")
    },
    {
        "order": 7,
        "question_type": "fill_blank",
        "question_instructions": "Complete the notes below. Write ONE WORD ONLY from the passage for each answer.",
        "question_text": "“Real tennis” court at Hampton Court: The ball may be hit against the ___ around the court",
        "correct_answer": "surfaces",
        "answer_location": "Paragraph 6",
        "passage_excerpt": "“Real tennis” is a remarkably fast and difficult game as the ball can be bounced off any of the surfaces, some of which are slanted at odd angles.",
        "what_question_asks": "What features or structural boundaries around the court the ball can bounce against during play.",
        "what_passage_says": "The text states that the ball can be 'bounced off any of the surfaces, some of which are slanted at odd angles'.",
        "why_answer": "'Surfaces' is the exact word in the text describing the court boundaries off which the ball is hit.",
        "paraphrase": "hit against the ___ -> bounced off any of the surfaces",
        "tip": "'Bounced off' corresponds to 'hit against'.",
        "options": []
    },
    {
        "order": 8,
        "question_type": "fill_blank",
        "question_instructions": "Complete the notes below. Write ONE WORD ONLY from the passage for each answer.",
        "question_text": "“Real tennis” court at Hampton Court: The ___ is lower in the centre",
        "correct_answer": "net",
        "answer_location": "Paragraph 6",
        "passage_excerpt": "The net is just over 1.5 metres high at each end, but drops to just under a metre in the middle.",
        "what_question_asks": "Which piece of court equipment has a lower height in the middle than at the ends.",
        "what_passage_says": "'The net is just over 1.5 metres high at each end, but drops to just under a metre in the middle.'",
        "why_answer": "The item that drops in height in the middle (centre) is the 'net'.",
        "paraphrase": "lower in the centre -> drops to just under a metre in the middle",
        "tip": "'Drops in the middle' directly matches 'is lower in the centre'.",
        "options": []
    },
    {
        "order": 9,
        "question_type": "fill_blank",
        "question_instructions": "Complete the notes below. Write ONE WORD ONLY from the passage for each answer.",
        "question_text": "1850s: Balls made out of ___ started to be used",
        "correct_answer": "rubber",
        "answer_location": "Paragraph 7",
        "passage_excerpt": "This led to the development of rubber tennis balls. During the 1850s, players began to experiment with these new balls",
        "what_question_asks": "What new material was used to manufacture tennis balls in the 1850s.",
        "what_passage_says": "Goodyear's vulcanisation 'led to the development of rubber tennis balls. During the 1850s, players began to experiment with these new balls'.",
        "why_answer": "The balls tested and used in the 1850s were made of 'rubber'.",
        "paraphrase": "balls made out of ___ started to be used -> development of rubber tennis balls ... players began to experiment with these new balls",
        "tip": "Locate the decade '1850s' in paragraph 7 to identify the material.",
        "options": []
    },
    {
        "order": 10,
        "question_type": "fill_blank",
        "question_instructions": "Complete the notes below. Write ONE WORD ONLY from the passage for each answer.",
        "question_text": "1874: Major Walter C. Wingfield published written ___ for the game",
        "correct_answer": "rules",
        "answer_location": "Paragraph 8",
        "passage_excerpt": "Major Walter C. Wingfield, known as “the father of lawn tennis,” had the idea of devising rules, which he published.",
        "what_question_asks": "What written material Wingfield formulated and published in 1874.",
        "what_passage_says": "Major Walter C. Wingfield 'had the idea of devising rules, which he published'.",
        "why_answer": "Wingfield formulated and published 'rules' for lawn tennis.",
        "paraphrase": "published written ___ -> devising rules, which he published",
        "tip": "'Devising rules, which he published' matches 'published written rules'.",
        "options": []
    },
    {
        "order": 11,
        "question_type": "fill_blank",
        "question_instructions": "Complete the notes below. Write ONE WORD ONLY from the passage for each answer.",
        "question_text": "1874: Produced complete sets of tennis ___ for sale",
        "correct_answer": "equipment",
        "answer_location": "Paragraph 8",
        "passage_excerpt": "He also introduced standardised equipment, including racquets, balls, posts, and a net, which he patented and sold in sets.",
        "what_question_asks": "What collective category of items (racquets, balls, posts, net) Wingfield packaged and sold in sets.",
        "what_passage_says": "Wingfield 'introduced standardised equipment, including racquets, balls, posts, and a net, which he patented and sold in sets'.",
        "why_answer": "'Equipment' is the exact word used to describe the patented sets of playing gear sold to the public.",
        "paraphrase": "complete sets of tennis ___ for sale -> standardised equipment ... sold in sets",
        "tip": "'Equipment' encompasses racquets, balls, posts, and net.",
        "options": []
    },
    {
        "order": 12,
        "question_type": "fill_blank",
        "question_instructions": "Complete the notes below. Write ONE WORD ONLY from the passage for each answer.",
        "question_text": "1874: Designed an unusual ___ for the court",
        "correct_answer": "shape",
        "answer_location": "Paragraph 8",
        "passage_excerpt": "Interestingly, his original court had the shape of an hourglass, with the net across its narrowest section.",
        "what_question_asks": "What geometrical characteristic of the court was uniquely shaped like an hourglass.",
        "what_passage_says": "Wingfield's original court 'had the shape of an hourglass, with the net across its narrowest section'.",
        "why_answer": "'Shape' is the exact word in the text indicating the hourglass contour of his court.",
        "paraphrase": "designed an unusual ___ for the court -> had the shape of an hourglass",
        "tip": "'Shape of an hourglass' corresponds to 'an unusual shape'.",
        "options": []
    },
    {
        "order": 13,
        "question_type": "fill_blank",
        "question_instructions": "Complete the notes below. Write ONE WORD ONLY from the passage for each answer.",
        "question_text": "1877: The first large ___ was held",
        "correct_answer": "tournament",
        "answer_location": "Paragraph 9",
        "passage_excerpt": "A major tennis tournament took place for the first time in Wimbledon, London in 1877",
        "what_question_asks": "What major competitive event occurred for the first time in Wimbledon in 1877.",
        "what_passage_says": "'A major tennis tournament took place for the first time in Wimbledon, London in 1877'.",
        "why_answer": "The event held for the first time in 1877 was a 'tournament'.",
        "paraphrase": "the first large ___ was held -> major tennis tournament took place for the first time",
        "tip": "'Major' matches 'large', and 'took place for the first time' matches 'the first ... was held'.",
        "options": []
    }
]

# Section 2 Questions
s2_questions = [
    {
        "order": 14,
        "question_type": "matching",
        "question_instructions": "Reading Passage 2 has seven paragraphs, numbered 14–20. Choose the correct heading for each paragraph from the list of headings below. Write the correct number, i–ix.",
        "question_text": "Section 14",
        "correct_answer": "v",
        "answer_location": "Paragraph 14",
        "passage_excerpt": "he gave thanks that he had been born at a time when traditional dependence on the teaching of the Greek philosopher Aristotle (384-322 BCE) had given way to a new philosophy, based on experiment and observation of the real world, that we now call science.",
        "what_question_asks": "Which heading captures the main theme of paragraph 14.",
        "what_passage_says": "Ray expressed gratitude for being born during an intellectual era where blind adherence to Aristotle was replaced by experimental science.",
        "why_answer": "Expressing gratitude for the scientific revolution in his era represents 'Ray’s appreciation of his contemporary academic culture' (heading v).",
        "paraphrase": "appreciation -> gave thanks; contemporary academic culture -> new philosophy based on experiment and observation",
        "tip": "'Gave thanks' indicates appreciation of the contemporary shift towards modern science.",
        "options": get_headings_options("v")
    },
    {
        "order": 15,
        "question_type": "matching",
        "question_instructions": "Reading Passage 2 has seven paragraphs, numbered 14–20. Choose the correct heading for each paragraph from the list of headings below. Write the correct number, i–ix.",
        "question_text": "Section 15",
        "correct_answer": "iii",
        "answer_location": "Paragraph 15",
        "passage_excerpt": "He was appointed Lecturer in Greek in 1651, Lecturer in Mathematics in 1653, and Lecturer in Humanities in 1655.",
        "what_question_asks": "Which heading best summarizes paragraph 15 detailing Ray's progression at Cambridge.",
        "what_passage_says": "Ray excelled at Cambridge, established a reputation as a brilliant student, and was appointed to three successive lectureships in Greek, Mathematics, and Humanities.",
        "why_answer": "His consecutive lectureships and student distinctions represent 'A succession of academic achievements' (heading iii).",
        "paraphrase": "succession of academic achievements -> solid start ... brilliant student ... appointed Lecturer in Greek ... Mathematics ... Humanities",
        "tip": "Sequential lecturer appointments in consecutive years point to a 'succession of academic achievements'.",
        "options": get_headings_options("iii")
    },
    {
        "order": 16,
        "question_type": "matching",
        "question_instructions": "Reading Passage 2 has seven paragraphs, numbered 14–20. Choose the correct heading for each paragraph from the list of headings below. Write the correct number, i–ix.",
        "question_text": "Section 16",
        "correct_answer": "ix",
        "answer_location": "Paragraph 16",
        "passage_excerpt": "Almost immediately after graduating, Ray also seems to have developed the interest to which he would devote the rest of his life: the study of the natural world.",
        "what_question_asks": "Which heading reflects the turning point in Ray's intellectual career in paragraph 16.",
        "what_passage_says": "Following an illness in his twenties, Ray turned from classics to studying the natural world and local flora, investigating it independently.",
        "why_answer": "The text describes this transformation as his 'conversion into a naturalist', matching 'A change of direction for Ray' (heading ix).",
        "paraphrase": "change of direction -> conversion into a naturalist - in particular into a botanist",
        "tip": "'Conversion into a naturalist' directly signifies a change of direction.",
        "options": get_headings_options("ix")
    },
    {
        "order": 17,
        "question_type": "matching",
        "question_instructions": "Reading Passage 2 has seven paragraphs, numbered 14–20. Choose the correct heading for each paragraph from the list of headings below. Write the correct number, i–ix.",
        "question_text": "Section 17",
        "correct_answer": "iv",
        "answer_location": "Paragraph 17",
        "passage_excerpt": "By the mid-1650s, even the first-year students at Trinity College were able to identify the plants and flowers around Cambridge, as they were being taught (unofficially - none of this was part of their formal education) by Ray.",
        "what_question_asks": "Which heading describes Ray's botanical instruction described in paragraph 17.",
        "what_passage_says": "Ray instructed first-year Cambridge students 'unofficially' because botany was not part of their formal university curriculum.",
        "why_answer": "Teaching students unofficially outside formal coursework matches 'Ray’s informal tuition' (heading iv).",
        "paraphrase": "informal tuition -> taught (unofficially - none of this was part of their formal education)",
        "tip": "'Unofficially' and 'not part of formal education' mean 'informal tuition'.",
        "options": get_headings_options("iv")
    },
    {
        "order": 18,
        "question_type": "matching",
        "question_instructions": "Reading Passage 2 has seven paragraphs, numbered 14–20. Choose the correct heading for each paragraph from the list of headings below. Write the correct number, i–ix.",
        "question_text": "Section 18",
        "correct_answer": "i",
        "answer_location": "Paragraph 18",
        "passage_excerpt": "I had first to become familiar with the literature, to compare the plants that I found with the pictures, and when there seemed to be a resemblance, to go fully into any unknown descriptions. Gaining skill by experience, I acquired at last the ability to recognise to what tribe and family similars could be assigned",
        "what_question_asks": "Which heading summarizes the detailed quote in paragraph 18.",
        "what_passage_says": "Ray explains his methodical process of reviewing literature, comparing specimens with pictures, and categorizing plants by family and tribe.",
        "why_answer": "This firsthand explanation of his research procedure constitutes 'Ray’s account of his working methods' (heading i).",
        "paraphrase": "account of his working methods -> I had first to become familiar with the literature, to compare ... gaining skill by experience",
        "tip": "First-person descriptions ('I had first to...', 'this taught me to...') describe working methods.",
        "options": get_headings_options("i")
    },
    {
        "order": 19,
        "question_type": "matching",
        "question_instructions": "Reading Passage 2 has seven paragraphs, numbered 14–20. Choose the correct heading for each paragraph from the list of headings below. Write the correct number, i–ix.",
        "question_text": "Section 19",
        "correct_answer": "viii",
        "answer_location": "Paragraph 19",
        "passage_excerpt": "It gave the names of plants found in the area around Cambridge and included information about where they grew and how common they were.",
        "what_question_asks": "Which heading captures the description of the Cambridge Catalogue in paragraph 19.",
        "what_passage_says": "The paragraph explains that the book gave plant names, their locations, and how common they were, providing practical value.",
        "why_answer": "Specifying what material was contained in the book matches 'A description of the content of Ray’s first book' (heading viii).",
        "paraphrase": "content of Ray's first book -> gave the names of plants ... where they grew and how common they were",
        "tip": "Listing what information a book provides is a description of its content.",
        "options": get_headings_options("viii")
    },
    {
        "order": 20,
        "question_type": "matching",
        "question_instructions": "Reading Passage 2 has seven paragraphs, numbered 14–20. Choose the correct heading for each paragraph from the list of headings below. Write the correct number, i–ix.",
        "question_text": "Section 20",
        "correct_answer": "vii",
        "answer_location": "Paragraph 20",
        "passage_excerpt": "With the support of Francis Willughby, he began to imagine a more comprehensive investigation of nature, one that would attempt to classify living things according to careful observation of their shared characteristics. This was an ambitious undertaking",
        "what_question_asks": "Which heading summarizes Ray's broader future aims in paragraph 20.",
        "what_passage_says": "With Willughby's support, Ray envisioned an ambitious undertaking to classify living organisms systematically according to shared characteristics.",
        "why_answer": "This comprehensive proposal represents 'Plans for a bold new project' (heading vii).",
        "paraphrase": "plans for a bold new project -> imagine a more comprehensive investigation of nature ... ambitious undertaking",
        "tip": "'Ambitious undertaking' directly signals a bold new plan.",
        "options": get_headings_options("vii")
    },
    {
        "order": 21,
        "question_type": "fill_blank",
        "question_instructions": "Complete the summary below. Write ONE WORD ONLY from the passage for each answer.",
        "question_text": "John Ray was a scholar and self-taught botanist, whose work reflected the ___ that was taking place during the 17th century in people’s way of thinking about the natural world.",
        "correct_answer": "revolution",
        "answer_location": "Paragraph 14",
        "passage_excerpt": "The 17th-century English scholar and botanist John Ray was well aware that he lived through, and participated in, a profound revolution in the way people interacted with nature.",
        "what_question_asks": "What single noun denotes the profound transformation occurring in 17th-century thought regarding nature.",
        "what_passage_says": "Ray recognized that he lived through 'a profound revolution in the way people interacted with nature'.",
        "why_answer": "'Revolution' is the exact word in paragraph 14 describing this intellectual shift.",
        "paraphrase": "reflected the ___ that was taking place -> lived through, and participated in, a profound revolution",
        "tip": "Match '17th-century' and 'way people interacted with nature'.",
        "options": []
    },
    {
        "order": 22,
        "question_type": "fill_blank",
        "question_instructions": "Complete the summary below. Write ONE WORD ONLY from the passage for each answer.",
        "question_text": "This new approach is the basis of the modern field of ___ .",
        "correct_answer": "science",
        "answer_location": "Paragraph 14",
        "passage_excerpt": "had given way to a new philosophy, based on experiment and observation of the real world, that we now call science.",
        "what_question_asks": "What modern discipline is based on experimental and observational philosophy.",
        "what_passage_says": "The experimental philosophy of the real world is what 'we now call science'.",
        "why_answer": "'Science' is the exact noun in the text identifying the modern field.",
        "paraphrase": "modern field of ___ -> that we now call science",
        "tip": "'That we now call' signals the modern name.",
        "options": []
    },
    {
        "order": 23,
        "question_type": "fill_blank",
        "question_instructions": "Complete the summary below. Write ONE WORD ONLY from the passage for each answer.",
        "question_text": "As Ray himself explained, his interest in plants was aroused after graduating, when he had to spend time outdoors after a period of ___ .",
        "correct_answer": "illness",
        "answer_location": "Paragraph 16",
        "passage_excerpt": "Ray tells us that he suffered an illness in his early twenties, and was advised to take long walks and ride in the fresh air while recovering.",
        "what_question_asks": "What medical condition caused Ray to walk in the fresh air, initiating his plant studies.",
        "what_passage_says": "Ray 'suffered an illness in his early twenties, and was advised to take long walks and ride in the fresh air while recovering'.",
        "why_answer": "'Illness' is the exact word describing what Ray suffered before spending time outdoors.",
        "paraphrase": "after a period of ___ -> suffered an illness ... while recovering",
        "tip": "'While recovering' indicates recovery from an illness.",
        "options": []
    },
    {
        "order": 24,
        "question_type": "fill_blank",
        "question_instructions": "Complete the summary below. Write ONE WORD ONLY from the passage for each answer.",
        "question_text": "He taught himself, in addition to many Cambridge ___ , and began compiling his catalogue of plants, which was published in 1660.",
        "correct_answer": "students",
        "answer_location": "Paragraph 17",
        "passage_excerpt": "By the mid-1650s, even the first-year students at Trinity College were able to identify the plants and flowers around Cambridge, as they were being taught (unofficially - none of this was part of their formal education) by Ray.",
        "what_question_asks": "Who at Cambridge received informal plant instruction from Ray.",
        "what_passage_says": "First-year 'students' at Trinity College, Cambridge were being taught informally by Ray.",
        "why_answer": "'Students' is the exact plural noun in paragraph 17 describing those Ray instructed.",
        "paraphrase": "in addition to many Cambridge ___ -> the first-year students at Trinity College ... being taught ... by Ray",
        "tip": "Ensure the plural form 'students' is preserved from the text.",
        "options": []
    },
    {
        "order": 25,
        "question_type": "mcq",
        "question_instructions": "Choose TWO correct answers. Which TWO of the following statements are true of Ray’s early life?",
        "question_text": "Which of the following statements is true of Ray’s early life? (Select first true statement)",
        "correct_answer": "C",
        "answer_location": "Paragraph 15",
        "passage_excerpt": "his talents were recognised by a church official, Samuel Covell, who had graduated from Cambridge University in 1600, and maintained his links with his university.",
        "what_question_asks": "Which statement about Ray's early years is factually verified by paragraph 15.",
        "what_passage_says": "Samuel Covell, who graduated from Cambridge in 1600, recognized Ray's talents and helped him gain admission to Cambridge.",
        "why_answer": "Covell was a graduate (former student) of Cambridge and facilitated Ray's admission, confirming Option C ('He was helped by a former student of Cambridge University').",
        "paraphrase": "helped by a former student of Cambridge University -> talents were recognised by a church official, Samuel Covell, who had graduated from Cambridge University in 1600 ... Through his influence, Ray was admitted",
        "tip": "'Graduated from Cambridge' means former student.",
        "options": get_choose_two_options("C")
    },
    {
        "order": 26,
        "question_type": "mcq",
        "question_instructions": "Choose TWO correct answers. Which TWO of the following statements are true of Ray’s early life?",
        "question_text": "Which of the following statements is true of Ray’s early life? (Select second true statement)",
        "correct_answer": "D",
        "answer_location": "Paragraph 15",
        "passage_excerpt": "His father was a village blacksmith, and his mother was also a respected member of the community, a healer who was an expert in folk medicine and the use of herbs to treat ailments.",
        "what_question_asks": "Which second statement regarding Ray's family and upbringing is supported by the text.",
        "what_passage_says": "His father served as the village blacksmith, and his mother was 'also a respected member of the community' as a herbal healer.",
        "why_answer": "Both parents were established, respected figures locally, confirming Option D ('His parents were both valued by the people in their local area').",
        "paraphrase": "parents were both valued by the people in their local area -> respected member of the community [describing his mother, alongside his father's established role as village blacksmith]",
        "tip": "'Respected member of the community' directly matches 'valued by the people in their local area'.",
        "options": get_choose_two_options("D")
    }
]

# Section 3 Questions
s3_questions = [
    {
        "order": 27,
        "question_type": "matching",
        "question_instructions": "Match each event with the correct date, A–H.",
        "question_text": "The first electric telegraph system was submitted to the Admiralty.",
        "correct_answer": "A",
        "answer_location": "Paragraph D",
        "passage_excerpt": "He was not the first to propose a system of this nature to them. Some ten years earlier, in 1806, the inventor Ralph Wedgwood had offered the Admiralty a similar type of telegraph based on frictional electricity, which it had rejected.",
        "what_question_asks": "Which date corresponds to the initial electric telegraph proposal presented to the Admiralty.",
        "what_passage_says": "In 1806, inventor Ralph Wedgwood offered the Admiralty a telegraph system, which was rejected.",
        "why_answer": "1806 (Option A) was the date when the first electric telegraph was submitted to the Admiralty.",
        "paraphrase": "submitted to the Admiralty -> offered the Admiralty a similar type of telegraph",
        "tip": "Wedgwood proposed his system in 1806, ten years before Ronalds contacted them in 1816.",
        "options": get_dates_options("A")
    },
    {
        "order": 28,
        "question_type": "matching",
        "question_instructions": "Match each event with the correct date, A–H.",
        "question_text": "Ronalds received official recognition of his contribution to telegraphy.",
        "correct_answer": "H",
        "answer_location": "Paragraph G",
        "passage_excerpt": "In 1870, three years before he died, he was knighted by Queen Victoria, a belated honour in recognition of his “early and remarkable labours in telegraphic investigations.”",
        "what_question_asks": "Which date marks Ronalds receiving formal state honours for his telegraph work.",
        "what_passage_says": "In 1870, Queen Victoria knighted Ronalds in recognition of his telegraphic labours.",
        "why_answer": "Ronalds was knighted in 1870 (Option H), providing official recognition of his work.",
        "paraphrase": "official recognition -> knighted by Queen Victoria, a belated honour in recognition",
        "tip": "Knighthood from the monarch is the quintessential form of 'official recognition'.",
        "options": get_dates_options("H")
    },
    {
        "order": 29,
        "question_type": "matching",
        "question_instructions": "Match each event with the correct date, A–H.",
        "question_text": "The first electric telegraph was patented.",
        "correct_answer": "E",
        "answer_location": "Paragraph G",
        "passage_excerpt": "in 1837 they developed the Wheatstone-Cooke five-needle telegraph. The pair patented their design in the same year, the first of its kind to be officially registered",
        "what_question_asks": "In what year the first official patent for an electric telegraph was registered.",
        "what_passage_says": "Wheatstone and Cooke developed their telegraph in 1837 and patented it in the same year as the first of its kind.",
        "why_answer": "The patent was registered in 1837 (Option E).",
        "paraphrase": "first electric telegraph was patented -> patented their design in the same year, the first of its kind to be officially registered",
        "tip": "'In the same year' refers directly to 1837.",
        "options": get_dates_options("E")
    },
    {
        "order": 30,
        "question_type": "matching",
        "question_instructions": "Match each event with the correct date, A–H.",
        "question_text": "Ronalds began to experiment with electricity.",
        "correct_answer": "B",
        "answer_location": "Paragraph A",
        "passage_excerpt": "This brought him into contact with the elderly Swiss meteorologist Jean Andre de Luc, who was also an inspired inventor in the field of electricity. In 1814, de Luc encouraged Ronalds to start work on this new discipline.",
        "what_question_asks": "Which year marks the beginning of Ronalds's electrical experiments.",
        "what_passage_says": "In 1814, Jean Andre de Luc encouraged Ronalds to begin work in electricity.",
        "why_answer": "Ronalds started working on electricity in 1814 (Option B).",
        "paraphrase": "began to experiment with electricity -> start work on this new discipline",
        "tip": "'Start work on this new discipline' directly matches 'began to experiment'.",
        "options": get_dates_options("B")
    },
    {
        "order": 31,
        "question_type": "matching",
        "question_instructions": "Match each event with the correct date, A–H.",
        "question_text": "Ronalds informed the public about the possible uses of his telegraph.",
        "correct_answer": "D",
        "answer_location": "Paragraph F",
        "passage_excerpt": "However, in a small pamphlet published in 1823, he described his invention and listed some of its potential uses.",
        "what_question_asks": "The question asks which date matches when Ronalds shared with the public how his telegraph could be used.",
        "what_passage_says": "The passage says 'in a small pamphlet published in 1823, he described his invention and listed some of its potential uses' — meaning 1823 is when he publicly explained potential applications.",
        "why_answer": "This directly confirms 1823 as when Ronalds told the public about his telegraph's uses, matching the question, so the answer is D.",
        "paraphrase": "question: 'Ronalds informed the public about the possible uses of his telegraph' → passage: 'in a small pamphlet published in 1823, he described his invention and listed some of its potential uses'",
        "tip": "💡 'Pamphlet published' is a clear way of sharing information with 'the public' — a direct match for this date's event.",
        "options": get_dates_options("D")
    },
    {
        "order": 32,
        "question_type": "short_answer",
        "question_instructions": "Answer the questions below. Write NO MORE THAN THREE WORDS AND/OR A NUMBER from the passage for each answer.",
        "question_text": "What was marked on the dials on Ronalds’s garden telegraph?",
        "correct_answer": "letters and numbers",
        "answer_location": "Paragraph C",
        "passage_excerpt": "At either end of the wire was a revolving disc, on which letters and numbers were engraved.",
        "what_question_asks": "What characters were engraved or displayed on the garden telegraph dials.",
        "what_passage_says": "At either end of the wire was a revolving disc 'on which letters and numbers were engraved'.",
        "why_answer": "'Letters and numbers' is the exact text describing what was marked on the revolving dials.",
        "paraphrase": "marked on the dials -> letters and numbers were engraved",
        "tip": "'Engraved on the revolving disc' is synonymous with 'marked on the dials'.",
        "options": []
    },
    {
        "order": 33,
        "question_type": "short_answer",
        "question_instructions": "Answer the questions below. Write NO MORE THAN THREE WORDS AND/OR A NUMBER from the passage for each answer.",
        "question_text": "What did Ronalds use to enclose the wires on his later version of the garden telegraph?",
        "correct_answer": "glass tubes",
        "answer_location": "Paragraph C",
        "passage_excerpt": "Ronalds soon developed a modified version of his invention in which the wire was encased in glass tubes and buried in the ground.",
        "what_question_asks": "What physical material enclosed the wires in Ronalds's modified underground design.",
        "what_passage_says": "Ronalds's modified version featured wire 'encased in glass tubes and buried in the ground'.",
        "why_answer": "'Glass tubes' were used to encase/enclose the wires.",
        "paraphrase": "enclose the wires -> wire was encased in glass tubes",
        "tip": "'Encased in' means enclosed.",
        "options": []
    },
    {
        "order": 34,
        "question_type": "short_answer",
        "question_instructions": "Answer the questions below. Write NO MORE THAN THREE WORDS AND/OR A NUMBER from the passage for each answer.",
        "question_text": "How far did Ronalds believe his telegraph could transmit information?",
        "correct_answer": "800 km",
        "answer_location": "Paragraph E",
        "passage_excerpt": "Ronalds believed that his invention was capable of carrying messages some 800 km",
        "what_question_asks": "What distance Ronalds claimed his telegraph could transmit messages.",
        "what_passage_says": "Ronalds believed his invention was 'capable of carrying messages some 800 km'.",
        "why_answer": "'800 km' is the exact distance stated in the passage.",
        "paraphrase": "transmit information -> carrying messages",
        "tip": "Include both the number and the unit: '800 km'.",
        "options": []
    },
    {
        "order": 35,
        "question_type": "short_answer",
        "question_instructions": "Answer the questions below. Write NO MORE THAN THREE WORDS AND/OR A NUMBER from the passage for each answer.",
        "question_text": "What did the communication system invented by Ralph Wedgwood use?",
        "correct_answer": "frictional electricity",
        "answer_location": "Paragraph D",
        "passage_excerpt": "He was not the first to propose a system of this nature to them. Some ten years earlier, in 1806, the inventor Ralph Wedgwood had offered the Admiralty a similar type of telegraph based on frictional electricity, which it had rejected.",
        "what_question_asks": "The question asks what kind of electricity Ralph Wedgwood's telegraph system relied on.",
        "what_passage_says": "The passage says Wedgwood's telegraph was 'based on frictional electricity' — meaning this specific type of electricity powered his invention.",
        "why_answer": "'Frictional electricity' is the exact phrase the passage uses, directly answering the question.",
        "paraphrase": "question: 'what did the communication system invented by Ralph Wedgwood use' → passage: 'a similar type of telegraph based on frictional electricity'",
        "tip": "💡 This is a direct match — 'frictional electricity' appears in the passage exactly as needed to answer the question.",
        "options": []
    },
    {
        "order": 36,
        "question_type": "matching",
        "question_instructions": "Which paragraph contains the following information? Write the correct letter, A–G.",
        "question_text": "a description of a commercial application for the electric telegraph",
        "correct_answer": "G",
        "answer_location": "Paragraph G",
        "passage_excerpt": "the people who benefited most directly from Ronalds’s telegraphic work were the physicist Charles Wheatstone and his business partner William Cooke. They saw the potential of a rapid communication system for the growing number of private railway companies",
        "what_question_asks": "Which paragraph describes a profitable commercial or business deployment of the telegraph.",
        "what_passage_says": "Wheatstone and Cooke recognized the commercial potential for private railway companies and made significant financial profit.",
        "why_answer": "The commercial application for private railway networks is detailed in Paragraph G.",
        "paraphrase": "commercial application -> potential of a rapid communication system for the growing number of private railway companies ... financial gain",
        "tip": "'Private railway companies' and 'financial gain' signify commercial applications.",
        "options": get_paras_options("G")
    },
    {
        "order": 37,
        "question_type": "matching",
        "question_instructions": "Which paragraph contains the following information? Write the correct letter, A–G.",
        "question_text": "a rejection of Ronalds’s invention",
        "correct_answer": "E",
        "answer_location": "Paragraph E",
        "passage_excerpt": "John Barrow, Secretary to the Admiralty, wrote back to Ronalds on 5 August, saying that “telegraphs of any kind are wholly unnecessary, and NO other than the one now in use will be adopted.”",
        "what_question_asks": "Which paragraph records the official refusal to adopt Ronalds's telegraph invention.",
        "what_passage_says": "John Barrow informed Ronalds that telegraphs were 'wholly unnecessary' and refused adoption.",
        "why_answer": "The Admiralty's outright rejection of Ronalds's system appears in Paragraph E.",
        "paraphrase": "rejection -> wholly unnecessary, and NO other than the one now in use will be adopted",
        "tip": "John Barrow's reply stating telegraphs are 'wholly unnecessary' is the explicit rejection.",
        "options": get_paras_options("E")
    },
    {
        "order": 38,
        "question_type": "matching",
        "question_instructions": "Which paragraph contains the following information? Write the correct letter, A–G.",
        "question_text": "a drawback of Ronalds’s invention",
        "correct_answer": "C",
        "answer_location": "Paragraph C",
        "passage_excerpt": "The system was slow and depended on the two dials staying in step, but it worked.",
        "what_question_asks": "Which paragraph describes a weakness or limitation of Ronalds's apparatus.",
        "what_passage_says": "Paragraph C notes that 'The system was slow and depended on the two dials staying in step'.",
        "why_answer": "Being slow and requiring dial synchronization were technical drawbacks, detailed in Paragraph C.",
        "paraphrase": "drawback -> system was slow and depended on the two dials staying in step",
        "tip": "'Slow' and 'depended on dials staying in step' describe technical drawbacks.",
        "options": get_paras_options("C")
    },
    {
        "order": 39,
        "question_type": "matching",
        "question_instructions": "Which paragraph contains the following information? Write the correct letter, A–G.",
        "question_text": "reference to the positive influence on Ronalds of a fellow scientist",
        "correct_answer": "A",
        "answer_location": "Paragraph A",
        "passage_excerpt": "This brought him into contact with the elderly Swiss meteorologist Jean Andre de Luc, who was also an inspired inventor in the field of electricity. In 1814, de Luc encouraged Ronalds to start work on this new discipline.",
        "what_question_asks": "Which paragraph mentions another scientist encouraging and inspiring Ronalds.",
        "what_passage_says": "Swiss meteorologist Jean Andre de Luc encouraged Ronalds to enter the field of electricity in 1814.",
        "why_answer": "De Luc's encouragement of Ronalds represents a positive scientific influence in Paragraph A.",
        "paraphrase": "positive influence on Ronalds of a fellow scientist -> de Luc encouraged Ronalds to start work on this new discipline",
        "tip": "'Encouraged Ronalds to start work' represents positive scientific influence.",
        "options": get_paras_options("A")
    },
    {
        "order": 40,
        "question_type": "matching",
        "question_instructions": "Which paragraph contains the following information? Write the correct letter, A–G.",
        "question_text": "reference to the adoption of one of Ronalds’s procedures in preference to that of another scientist",
        "correct_answer": "F",
        "answer_location": "Paragraph F",
        "passage_excerpt": "A similar system was developed independently by Charles Brooke, but the British Association of Meteorologists confirmed Ronalds’s priority.",
        "what_question_asks": "The question asks which paragraph shows Ronalds's method being officially chosen over a rival scientist's similar idea.",
        "what_passage_says": "The passage says Charles Brooke developed 'a similar system', but 'the British Association of Meteorologists confirmed Ronalds's priority' — meaning Ronalds's method was officially recognized as coming first, ahead of Brooke's.",
        "why_answer": "This directly shows Ronalds's approach being favoured over another scientist's similar one, matching the question, so section F is the answer.",
        "paraphrase": "question: \"reference to the adoption of one of Ronalds's procedures in preference to that of another scientist\" → passage: \"a similar system was developed independently by Charles Brooke, but the British Association of Meteorologists confirmed Ronalds's priority\"",
        "tip": "💡 'Confirmed Ronalds's priority' over Brooke's similar system directly shows Ronalds's method being favoured.",
        "options": get_paras_options("F")
    }
]

# Verify excerpts exist in passages
def verify_excerpts():
    print("Verifying Section 1 excerpts...")
    for q in s1_questions:
        if q['passage_excerpt']:
            if q['passage_excerpt'] not in p1_text:
                print(f"FAILED S1 Q{q['order']}: excerpt not in passage!\n{q['passage_excerpt']}")
                return False
    print("Verifying Section 2 excerpts...")
    for q in s2_questions:
        if q['passage_excerpt']:
            if q['passage_excerpt'] not in p2_text:
                print(f"FAILED S2 Q{q['order']}: excerpt not in passage!\n{q['passage_excerpt']}")
                return False
    print("Verifying Section 3 excerpts...")
    for q in s3_questions:
        if q['passage_excerpt']:
            if q['passage_excerpt'] not in p3_text:
                print(f"FAILED S3 Q{q['order']}: excerpt not in passage!\n{q['passage_excerpt']}")
                return False
    print("ALL EXCERPTS VERIFIED PERFECTLY!")
    return True

if not verify_excerpts():
    sys.exit(1)

# Build full JSON payload
mock_test_5 = {
    "test_number": 5,
    "title": "IELTS Academic Mock Test 5",
    "description": "Full-length IELTS Academic Reading practice test featuring 3 passages (The Origins of Tennis, John Ray and the Study of Plants, and Sir Francis Ronalds) with 40 questions and comprehensive explanation breakdowns.",
    "modules": [
        {
            "module_type": "reading",
            "duration_minutes": 60,
            "instructions": "Read each passage and answer the questions.",
            "sections": [
                {
                    "order": 1,
                    "title": "Reading Passage 1: The Origins of Tennis",
                    "passage_instructions": "You should spend about 20 minutes on Questions 1–13, which are based on Reading Passage 1 below.",
                    "passage": p1_text,
                    "questions": s1_questions
                },
                {
                    "order": 2,
                    "title": "Reading Passage 2: John Ray and the Study of Plants",
                    "passage_instructions": "You should spend about 20 minutes on Questions 14–26, which are based on Reading Passage 2 below.",
                    "passage": p2_text,
                    "questions": s2_questions
                },
                {
                    "order": 3,
                    "title": "Reading Passage 3: Sir Francis Ronalds 1788–1873",
                    "passage_instructions": "You should spend about 20 minutes on Questions 27–40, which are based on Reading Passage 3 below.",
                    "passage": p3_text,
                    "questions": s3_questions
                }
            ]
        }
    ]
}

out_path = Path("mock_test_5.json")
out_path.write_text(json.dumps(mock_test_5, indent=2, ensure_ascii=False), encoding='utf-8')
print(f"Wrote {len(json.dumps(mock_test_5))} bytes to {out_path.resolve()}")

