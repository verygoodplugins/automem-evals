"""Frozen chunk and BM25 helpers from the earlier full-text protocol."""
from collections import Counter
import math
import re

STOP = frozenset('a an and are as at be before by could did do does for from has have how i in is it must of on or our should that the their they this to was were what when where which who why with would you'.split())


def tokens(text):
    return [x for x in re.findall(r'[a-z0-9]+', text.lower()) if len(x)>1 and x not in STOP]


def chunks(text, width=60, overlap=10):
    if not 0 <= overlap < width:
        raise ValueError('invalid chunk overlap')
    words=text.split()
    return [' '.join(words[i:i+width]) for i in range(0, len(words), width-overlap)]


def build_lexical(docs, field):
    rows=[Counter(tokens(d[field])) for d in docs]
    df=Counter(t for row in rows for t in row)
    lengths=[sum(row.values()) for row in rows]
    return rows,df,lengths, sum(lengths)/len(lengths)


def bm25(query, row, df, lengths, avg_length, index, n):
    total=0.0
    for token in set(tokens(query)):
        freq=row.get(token,0)
        if not freq: continue
        idf=math.log(1+(n-df[token]+0.5)/(df[token]+0.5))
        total+=idf*(freq*2.2)/(freq+1.2*(0.25+0.75*lengths[index]/avg_length))
    return total
