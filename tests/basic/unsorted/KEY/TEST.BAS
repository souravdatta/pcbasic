10 REM PC-BASIC test 
20 REM KEY syntax
30 OPEN "OUTPUT.TXT" FOR OUTPUT AS 1
40 ON ERROR GOTO 10000
50 KEY
60 KEY ON
70 KEY OFF
80 KEY LIST
85 KEY STOP
90 KEY PRINT
100 KEY,
105 KEY A$
110 KEY 1,
120 KEY 1, "asdf"
130 KEY 15, "asdf"
140 KEY 1, "as"
150 KEY 15, "as"
160 KEY 1, 2
170 KEY 15, 2
180 KEY (1)
190 KEY (1) ON
200 KEY (1) OFF
210 KEY (1) STOP
220 KEY (1) LIST
230 KEY (1) PRINT
240 KEY 1+1, "asdf"
250 KEY (1+1), "asdf"
260 KEY 1+1 STOP
270 KEY (1+1) STOP
280 KEY (1) STOP LAH
290 KEY 1,2,
300 KEY 1,2 LAH
310 KEY LIST LAH
9999 END
10000 PRINT#1, ERR, ERL
10010 RESUME NEXT
