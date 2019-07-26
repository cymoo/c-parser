#include <stdio.h>
#include <stdlib.h>

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
    printf("%d + %d = %d\n", x, y, add(x, y));
    printf("max(%d, %d) = %d\n", x, y, MAX(x, y));
    return 0;
}
