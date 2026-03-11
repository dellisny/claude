#include <stdio.h>
#include <string.h>

void reverse_and_print(char *input) {
    char buf[8];
    int len = strlen(input);

    /* copy input into fixed 8-byte buffer — no bounds check */
    strcpy(buf, input);

    /* reverse in place */
    for (int i = 0, j = len - 1; i < j; i++, j--) {
        char tmp = buf[i];
        buf[i]   = buf[j];
        buf[j]   = tmp;
    }

    printf("%s\n", buf);
}

int main(int argc, char *argv[]) {
    if (argc != 2) {
        fprintf(stderr, "usage: snake <string>\n");
        return 1;
    }

    reverse_and_print(argv[1]);
    return 0;
}
