10 OPEN "output.txt" FOR OUTPUT AS 1
2000 FOR C = 0 TO 255
2020 LPRINT, CHR$(C);:PRINT#1, C, LPOS(0)
2030 NEXT:LPRINT

