str = input("Enter your Email: ")

k,d ,p = 0,0,0

if len(str) >= 6:
    if str[0].isalpha():
        if ("@" in str) and (str.count("@") == 1):
            for i in str:
                if i==i.isspace():
                    k = 1
                elif i.isalpha():
                    if i==i.upper():
                        d = 1
                elif i.isdigit():
                    continue
                elif i=="_" or i=="@" or i==".":
                    continue
                else:
                    p = 1
            if (k == 1) or (d == 1) or (k == 1):
                print("Wrong Email.")
            else:
                print("Right Email.")
        else:
            print("Wrong Email.")
    else:
        print("Wrong Email.")
else:
    print("Wrong Email.")
    
