import iisignature, unittest, numpy

#text, index -> (either number or [res, res]), newIndex
def parseBracketedExpression(text,index):
    if(text[index]=='['):
        left, m = parseBracketedExpression(text,index+1)
        right, n = parseBracketedExpression(text,m+1)
        return [left,right],n+1
    else:
        n = 0
        while(n<len(text) and text[index+n] in ['1','2','3','4','5','6','7','8','9']): #this should always just happen once if input is a bracketed expression of letters
            n = n + 1
        return int(text[index:index+n]), index+n

#print (parseBracketedExpression("[23,[2,[[22,1],2]]]",0))

#bracketed expression, dim -> numpy array of its value, depth
def multiplyOut(expn, dim):
    if isinstance(expn,list):
        left, leftDepth  = multiplyOut(expn[0],dim)
        right,rightDepth = multiplyOut(expn[1],dim)
        a = numpy.outer(left,right).flatten()
        b = numpy.outer(right,left).flatten()
        return a-b, leftDepth+rightDepth
    else:
        a = numpy.zeros(dim)
        a[expn-1]=1
        return a,1

#string of bracketed expression, dim -> numpy array of its value, depth
#for example:
#valueOfBracket("[1,2]",2) is ([0,1,-1,0],2)
def valueOfBracket(text,dim):
    return multiplyOut(parseBracketedExpression(text,0)[0],dim)


#inputs are values in the tensor algebra given as lists of levels (from 1 to level), assumed 0 in level 0.
#returns their concatenation product
def multiplyTensor(a,b):
    level = len(a)
    dim = len(a[0])
    sum = [numpy.zeros(dim**m) for m in range(1,level+1)]
    for leftLevel in range(1,level):
        for rightLevel in range(1, 1+level-leftLevel):
            sum[leftLevel+rightLevel-1]+=numpy.outer(a[leftLevel-1],b[rightLevel-1]).flatten()
    return sum

#input is a value in the tensor algebra given as lists of levels (from 1 to level), assumed 0 in level 0.
#returns its exp - assumed 1 in level 0
#exp(x)-1 = x+x^2/2 +x^3/6 +x^4/24 + ...
def exponentiateTensor(a):
    out = [i.copy() for i in a]
    level = len(a)
    products = [out]
    for m in range(2,level+1):
        t=multiplyTensor(a,products[-1])
        for j in t:
            j *= (1.0/m)
        products.append(t)
    return [numpy.sum([p[i] for p in products],0) for i in range(level)]

#input is a value in the tensor algebra given as lists of levels (from 1 to level), assumed 1 in level 0.
#returns its exp - assumed 0 in level 0
#log(1+x) = x -x^2/2 +x^3/3 -x^4/4 + ...
def logTensor(a):
    out = [i.copy() for i in a]
    level = len(a)
    products = [out]
    for m in range(2,level+1):
        t=multiplyTensor(a,products[-1])
        products.append(t)
    neg=True
    for m in range(2,level+1):
        for j in products[m-1]:
            if neg:
                j *= (-1.0/m)
            else:
                j *= (1.0/m)
        neg = not neg
    return [numpy.sum([p[i] for p in products],0) for i in range(level)]

#given a tensor as a concatenated 1D array, return it as a list of levels
def splitConcatenatedTensor(a, dim, level):
    start=0
    out=[]
    for m in range(1,level+1):
        levelLength = dim**m
        out.append(a[start:(start+levelLength)])
        start=start + levelLength
    assert(start==a.shape[0])
    return out

#This test checks that basis, logsig and sig are compatible with each other by calculating a signature both using sig
#and using logsig and checking they are equal 
class A(unittest.TestCase):
    def testa(self):
        #numpy.random.seed(21)
        dim=3
        level = 4
        s = iisignature.prepare(dim,level,"cosx")
        path = numpy.random.uniform(size=(10,dim))
        basis = iisignature.basis(s)
        logsig = iisignature.logsig(path,s)
        sig = iisignature.sig(path,level)

        #check lengths
        self.assertEqual(len(basis),iisignature.logsiglength(dim,level))
        self.assertEqual((len(basis),),logsig.shape)
        self.assertEqual(sig.shape,(iisignature.siglength(dim,level),))

        #calculate a signature from logsig
        expanded_logsig = [numpy.zeros(dim**m) for m in range(1,level+1)]
        for coeff, expression in zip(logsig,basis):
            values, depth  = valueOfBracket(expression,dim)
            expanded_logsig[depth-1]+=values*coeff
        calculated_sig = numpy.concatenate(exponentiateTensor(expanded_logsig))
        diff = numpy.max(numpy.abs(sig-calculated_sig))
        self.assertLess(diff,0.00001)

        #calculate a log signature from sig
        fullLogSig = numpy.concatenate(logTensor(splitConcatenatedTensor(sig,dim,level)))
        fullLogSigLib = iisignature.logsig(path,s,"x")
        diff1 = numpy.max(numpy.abs(fullLogSigLib-fullLogSig))
        #print (numpy.vstack([fullLogSig,fullLogSigLib,numpy.abs(fullLogSigLib-fullLogSig)]).transpose())
        self.assertLess(diff1,0.00001)

        basisMatrix=[]
        zeros = [numpy.zeros(dim**m) for m in range(1,level+1)]
        for expression in basis:
            values, depth = valueOfBracket(expression, dim)
            temp = zeros[depth-1]
            zeros[depth-1]=values
            basisMatrix.append(numpy.concatenate(zeros))
            zeros[depth-1]=temp
        calculatedLogSig=numpy.linalg.lstsq(numpy.transpose(basisMatrix),fullLogSig)[0]
        diff2 = numpy.max(numpy.abs(logsig-calculatedLogSig))
        self.assertLess(diff2,0.00001)

        #check consistency of methods
        slowLogSig = iisignature.logsig(path,s,"o")
        diffs = numpy.max(numpy.abs(slowLogSig-calculatedLogSig))
        self.assertLess(diffs,0.00001)

        sigLogSig = iisignature.logsig(path,s,"s")
        diffs = numpy.max(numpy.abs(sigLogSig-calculatedLogSig))
        self.assertLess(diffs,0.00001)

    #test sigjoin is compatible with sig and also its deriv
    def testjoining(self):
        numberToDo=1
        dim=2
        level = 2
        siglength = iisignature.siglength(dim,level)
        for fixedPoint, inputDim, fixed in [(float('nan'),dim,False),(0.1,dim-1,True)]:
            pathLength = 10
            def makePath():
                p = numpy.random.uniform(size=(pathLength,dim))
                if fixed:
                    p[:,-1]=fixedPoint*numpy.arange(pathLength)
                return p
            paths = [makePath() for i in range(numberToDo)]
            sig = numpy.vstack([iisignature.sig(path,level) for path in paths])

            joinee = numpy.zeros((numberToDo,siglength))
            for i in range(1,pathLength):
                displacements=[path[i:(i+1),:]-path[(i-1):i,:] for path in paths]
                displacement = numpy.vstack(displacements)
                if fixed:
                    displacement = displacement[:,:-1]
                joinee = iisignature.sigjoin(joinee,displacement,level,fixedPoint)
            diff=numpy.max(numpy.abs(sig-joinee))
            self.assertLess(diff,0.0001)

            extra = numpy.random.uniform(size=(numberToDo,inputDim))
            bumpedExtra = 1.001*extra
            bumpedJoinee = 1.001*joinee
            base = numpy.sum(iisignature.sigjoin(joinee,extra,level,fixedPoint))
            bump1 = numpy.sum(iisignature.sigjoin(bumpedJoinee,extra,level,fixedPoint))
            bump2 = numpy.sum(iisignature.sigjoin(joinee,bumpedExtra,level,fixedPoint))
            derivsOfSum = numpy.ones((numberToDo,siglength))
            calculated = iisignature.sigjoinbackprop(derivsOfSum,joinee,extra,
                                                     level,fixedPoint)
            diff1 = (bump1-base)-numpy.sum(calculated[0]*(bumpedJoinee-joinee))
            diff2 = (bump2-base)-numpy.sum(calculated[1]*(bumpedExtra-extra))
            self.assertLess(diff1,0.00001)
            self.assertLess(diff2,0.0001)

#test that sigjacobian and sigbackprop compatible with sig
class Deriv(unittest.TestCase):
    def testa(self):
        numpy.random.seed(291)
        d = 3
        m = 5
        pathLength = 10
        path = numpy.random.uniform(size=(pathLength,d))
        path = numpy.cumsum(2*(path-0.5),0)#makes it more random-walk-ish, less like a scribble
        increment = 0.01*numpy.random.uniform(size=(pathLength,d))
        base_sig = iisignature.sig(path,m)

        bumped_sig = iisignature.sig(path+increment,m)
        target = bumped_sig - base_sig
        
        gradient = iisignature.sigjacobian(path,m)
        calculated = numpy.tensordot(increment,gradient)

        diffs = numpy.max(numpy.abs(calculated-target))
        niceOnes=numpy.abs(calculated)>1.e-4
        niceOnes2=numpy.abs(calculated)<numpy.abs(base_sig)
        diffs1 = numpy.max(numpy.abs((calculated[niceOnes2]-target[niceOnes2])/base_sig[niceOnes2]))
        diffs2 = numpy.max(numpy.abs(calculated[1-niceOnes2]-target[1-niceOnes2]))
        ratioDiffs = numpy.max(numpy.abs(calculated[niceOnes]/target[niceOnes]-1))

        #numpy.set_printoptions(suppress=True,linewidth=os.popen('stty size', 'r').read().split()[1] #LINUX
        #numpy.set_printoptions(suppress=True,linewidth=150)
        #print ("")
        #print (path)
        #print (numpy.vstack([range(len(base_sig)),base_sig,calculated,target,(calculated-target)/base_sig,calculated/target-1]).transpose())
        #print (diffs, diffs1, diffs2, ratioDiffs, numpy.argmax(numpy.abs(calculated[niceOnes]/target[niceOnes]-1)),numpy.argmax(numpy.abs((calculated-target)/base_sig)))

        #These assertions are pretty weak, the small answers are a bit volatile
        self.assertLess(diffs,0.0001)
        self.assertLess(ratioDiffs,0.2)
        self.assertLess(diffs1,0.05) 
        self.assertLess(diffs2,0.00001) 

        #compatibility between sigbackprop and sigjacobian is strong
        dFdSig = numpy.random.uniform(size=(iisignature.siglength(d,m),))
        backProp = iisignature.sigbackprop(dFdSig,path,m)
        manualCalcBackProp = numpy.dot(gradient,dFdSig)
        backDiffs = numpy.max(numpy.abs(backProp-manualCalcBackProp))
        self.assertLess(backDiffs,0.000001)

        

