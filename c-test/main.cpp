#include <stdio.h>

#define MAX(x, y) (x) > (y) ? (x) : (y)
#define FOO 123
#define EXPORTED
struct StringArray {
    char **arr;
    size_t size;
};
typedef struct StringArray *sap;

sap bar(sap s);

int gv1 = 13;
int gv2;

EXPORTED int add(int, int);

namespace ns {
    int add1(int x) {
        return x + 1;
    }
    int add2(int y);

    class Foo {
    public:
        int aa(int x)
        {
            return ns::add2(x);
        }
    };
}

int ns::add2(int y){
    return y + 2;
}

double min(double x, double y, double z)
{
    double tmp = x > y ? y : x;
    return tmp > z ? z : tmp;
}

EXPORTED int add(int x, int y)
{
    return x + y;
}

static void static_func()
{
    printf("it's a static function");
}

sap bar(sap s)
{
    return NULL;
}

int main(void)
{
    int x = 13;
    int y = 31;
    double a = 13.1;
    double b = 23.5;
    double c = 7.9;
    ns::Foo f;
    printf("%d + %d = %d\n", x, y, add(x, y));
    printf("MAX(%d, %d) = %d\n", x, y, MAX(x, y));
    printf("main(%f, %f, %f) = %f\n", a, b, c, min(a, b, c));
    printf("%d + 1 = %d\n", x, ns::add1(x));
    printf("f.aa(%d)=%d\n", y, f.aa(y));
    return 0;
}
