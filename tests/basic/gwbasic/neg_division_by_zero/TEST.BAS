10 ' test float and integer division by zero 
25 ? (-1.)/0/0
31 ? (-1#)/0/0
33 ? (-1)\0
35 ? (-1) MOD 0
39 on error goto 500
50 ? (-1)\0\0
57 ? (-1) MOD 0 MOD 0
60 end
500 print "error:", err, erl
510 resume next
1000 N$="output.txt" ' RUN 1000 to dump screen
1010 DEF SEG=&HB800
1020 OPEN N$ FOR OUTPUT AS 1
1030 FOR Y = 0 TO 24
1040 FOR X = 0 TO 79
1050 PRINT #1, CHR$(PEEK(2*(Y*80+X)));
1060 NEXT
1065 PRINT #1, ""
1070 NEXT
1080 CLOSE 1

