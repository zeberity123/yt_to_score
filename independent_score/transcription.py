"""Hand-entered visual transcription of wpme40lu_XE, independent of drumscore.

Tokens: string/fret:quarter-note duration[:marks]. R is a rest. Marks:
i/o slide in/out, t tied forward, c parenthesized continuation, h hammer-on
to following note, S/P slap/pop, v vibrato. Numeric string order G D A E.
This file contains visual decisions, not an automatic extraction algorithm.
"""
from copy import deepcopy

def parse(text):
    events=[]
    for token in text.split():
        pitch,duration,*marks=token.split(':')
        events.append(dict(string=None if pitch=='R' else pitch[0],
                           fret=None if pitch=='R' else pitch[1:],
                           duration=float(duration),marks=marks[0] if marks else ''))
    return events

bars={}
def put(number,text): bars[number]=parse(text)
def repeat(number,source): bars[number]=deepcopy(bars[source])
def eighths(number,string,frets,first='',last=''):
    values=frets.split()
    put(number,' '.join(f'{string}{f}:.5:{first if i==0 else last if i==len(values)-1 else ""}' for i,f in enumerate(values)))
def eight(number,string,fret,first='',last=''):
    eighths(number,string,' '.join([str(fret)]*8),first,last)

for n in range(1,8): put(n,'R:4')
put(8,'R:2 R:1.5 E6:.5:t')
put(9,'E6:.5:c E6:.5 A9:1:i A9:1.5:o A4:.5:t')
put(10,'A4:.5:c A4:.5 R:.5 A8:1:i A6:1 E6:.5:t')
repeat(11,9)
put(12,'A4:.5:c A4:.5 R:.5 A9:.5:h A11:.5 D13:1 E6:.5:t')
for n in range(13,28): repeat(n,{1:9,2:10,3:9,0:12}[n%4])
put(28,'A4:.5:c A4:.5 R:.5 D6:.5:i R:2')
put(29,'E6:1 '+' '.join(['E6:.5']*6))
eighths(30,'E','6 6 6 6 6 6 8 8')
eight(31,'E',9)
put(32,' '.join(['E9:.5']*6+['A8:.5']*2))
eight(33,'A',6)
eight(34,'A',6,last='o')
eight(35,'A',7,first='i',last='o')
put(36,'D10:.5:i G8:.5 D10:.5 G8:.25:h G10:.75 D10:.5 A8:1')
eight(37,'E',6)
repeat(38,30)
eight(39,'A',4)
put(40,'A4:.5 A4:.5 D6:.5 A4:.5 A4:.5 D6:.5 A4:.5 A4:.5')
eight(41,'A',6)
put(42,'A6:.5 D8:.5 A6:.5 D10:1:i D8:.5 A9:.5 A8:.5')
eight(43,'A',7,last='o')
put(44,'A8:.5 A8:.5 A8:.5 A15:1:i D15:.5 A15:1:o')
eight(45,'E',6)
repeat(46,30)
eight(47,'E',9)
eight(48,'E',9)
eight(49,'A',6)
eight(50,'A',6)
eight(51,'A',7)
put(52,' '.join(['A8:.5']*6+['A8:1:o']))
eighths(53,'E','6 X X 6 X X 6 X')
eighths(54,'E','X 6 X X 6 6 8 8')
eighths(55,'A','4 X X 4 X X 4 X')
put(56,'AX:.5 A4:.5 AX:.5 AX:.5 A4:.5 A6:1.5:o')
eighths(57,'E','4 X X 4 X X 4 X')
put(58,'EX:.5 E4:.5 EX:.5 EX:.5 E4:.5 A6:.5 E3:1')
put(59,'E2:.5 EX:.5 EX:.5 E2:.5 EX:.5 EX:.5 E1:1')
put(60,'R:.5 E1:.5 EX:.5 EX:.5 E1:.5 E1:.5 E5:1')
for n in range(61,67): repeat(n,n-8)
put(67,'E2:.5 EX:.5 EX:.5 E2:.5 EX:.5 EX:.5 E2:1')
repeat(68,60)
put(69,'E6:.5 R:.5 E6:.5 R:.5 E6:.5 E6:.5 R:.5 E4:.5')
put(70,'R:.5 E4:.5 R:.5 E4:.5 R:.5 E4:.5 A6:.5 E4:.5')
put(71,'E2:.5 R:.5 E2:.5 R:.5 E2:.5 E2:.5 R:.5 E1:.5')
put(72,'R:.5 E1:.5 R:.5 E1:.5 E1:.5 E1:.5 E5:1:i')
put(73,'E6:.5 R:.5 E6:.5 R:.5 E6:.5 A8:.5 E6:.5 E4:.5')
put(74,'R:.5 E4:.5 A6:.5 D8:1:i D6:.5 A6:.5 E4:.5')
put(75,'E2:.5 R:.5 E2:.5 R:.5 E2:.5 A4:.5 E2:.5 E1:.5')
put(76,'R:4')
repeat(77,29)
repeat(78,30)
repeat(79,31)
repeat(80,32)
eight(81,'A',6)
eight(82,'A',6)
eight(83,'A',7)
repeat(84,36)
eight(85,'E',6)
eighths(86,'E','6 6 6 4 6 4 6 8')
eight(87,'A',4)
eight(88,'A',4)
eight(89,'A',6)
repeat(90,42)
repeat(91,43)
repeat(92,44)
put(93,'A4:.5:S AX:.25:S G6:.25:P AX:.25:S G6:.25:P D4:.5:S D6:.5:S AX:.25:S D6:.25:P AX:.25:S D6:.25:P A4:.5:S')
put(94,'D2:.5:P AX:.25:S D4:.25:P R:.25 DX:.25:P E4:.5:S A2:1:S A4:1:S')
for n in (95,97,99): repeat(n,93)
for n in (96,98): repeat(n,94)
put(100,'D2:.5:P AX:.25:S D4:.25:P R:.25 DX:.25:P E4:.5:S R:1 R:1')
eight(101,'E',6)
eighths(102,'E','6 6 6 6 6 8 8 8')
eight(103,'A',4)
put(104,'A4:.5 A4:.5 A4:.5 A4:.5 A4:1 A4:.5 A4:.5')
put(105,'A11:.5:i A11:.5 A11:.5 A11:.5 A11:1 A11:.5 A11:.5')
put(106,'A12:.5 A12:.5 A12:.5 A12:.5 A12:1 A12:.5 A12:.5')
put(107,'A9:.5 A9:.5 A9:.5 A9:.5 A9:1 A9:.5 A9:.5')
put(108,'A9:.5 A9:.5 A9:.5 A9:.5 A9:1 A9:1')
eight(109,'E',6)
repeat(110,30)
eight(111,'A',4)
put(112,' '.join(['A4:.5']*6+['A4:1:o']))
eight(113,'E',2)
put(114,' '.join(['E2:.5']*6+['A2:1:u']))
eight(115,'A',8)
put(116,'R:4')
put(117,'R:4')
put(118,'A2:1 '+' '.join(['A2:.5']*6))
eighths(119,'A','2 2 2 2 2 2 4 4')
eight(120,'A',5)
put(121,' '.join(['A5:.5']*6+['A9:.5:i','A9:.5']))
eight(122,'A',7)
eight(123,'A',7,last='o')
eight(124,'A',8,first='i',last='o')
put(125,'D11:.5:i G9:.5 D11:.5 G9:.25:h G11:.75 D11:.5 A9:1')
put(126,'E7:1 E7:.5 E7:.5 E7:.5 E7:.5 E7:.5 E5:.5')
put(127,'E7:.5 E7:.5 E7:.5 E5:.5 E7:1:o E7:.5:i E9:.5')
eighths(128,'A','5 5 5 5 5 5 7 7')
put(129,'A12:.5 D12:.5 A12:.5 D14:1:i D12:.5 A12:.5 A12:.5')
put(130,'A7:1 A7:.5 A7:.5 A7:.5 A7:.5 D9:.5 A7:.5')
put(131,'A7:.5 D9:.5 A7:.5 D11:1:i D9:.5 A10:.5 A9:.5')
put(132,'A8:1 A8:.5 A16:1:i D14:.5 A16:.5 D14:.25:h D16:.25:t')
put(133,'D16:.5:c G15:.5 D16:.5 G16:1:i D16:.5 A16:1')
put(134,'E7:1 '+' '.join(['E7:.5']*6))
put(135,'E7:.5 E7:.5 E7:.5 E7:.5 E7:1 E9:1')
eight(136,'A',5)
eight(137,'A',5)
eight(138,'A',7)
eight(139,'A',7)
put(140,'A8:1 '+' '.join(['A8:.5']*6))
put(141,'A9:1 A9:.5 A16:1:i D16:.5 A16:1:o')
put(142,'E7:2:tv E7:2:cov')
put(143,'R:4')

# Inspection references are source-video seconds, not app extraction results.
references=[(1,8,5),(9,12,20),(13,16,25),(17,20,35),(21,24,40),
 (25,28,45),(29,30,47),(31,35,55),(36,38,60),(39,42,70),
 (43,46,75),(47,48,79),(49,54,85),(55,60,94),(61,68,108),
 (69,75,116),(76,80,125),(81,86,140),(87,92,150),(93,96,154),
 (97,100,162),(101,103,168),(104,106,173),(107,110,180),
 (111,115,190),(116,120,195),(121,125,205),(126,128,211),
 (129,131,215),(132,135,218),(136,139,225),(140,143,235)]

def validate():
    assert sorted(bars)==list(range(1,144))
    for n,events in bars.items():
        assert abs(sum(e['duration'] for e in events)-4)<1e-9, (n,events)
        for i,e in enumerate(events):
            if 't' in e['marks']:
                following=events[i+1] if i+1<len(events) else bars[n+1][0]
                assert e['string']==following['string'] and e['fret']==following['fret'],n
                assert 'c' in following['marks'],n

if __name__=='__main__':
    validate()
    print(f'{len(bars)} bars; all sum to 4 beats; ties agree.')
