#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

#define MAX_VALS    100
#define STATE_FILE  ".btree"

typedef struct Node {
    int val;
    struct Node *left, *right;
} Node;

static int  vals[MAX_VALS];
static int  nvals;
static char state_path[512];

static void
init_path(void)
{
    const char *home = getenv("HOME");
    if (home)
        snprintf(state_path, sizeof state_path, "%s/%s", home, STATE_FILE);
    else
        snprintf(state_path, sizeof state_path, "%s", STATE_FILE);
}

static void
load(void)
{
    FILE *f = fopen(state_path, "r");
    if (!f) return;
    while (nvals < MAX_VALS && fscanf(f, "%d", &vals[nvals]) == 1)
        nvals++;
    fclose(f);
}

static void
save(void)
{
    FILE *f = fopen(state_path, "w");
    if (!f) { perror(state_path); exit(1); }
    for (int i = 0; i < nvals; i++)
        fprintf(f, i ? " %d" : "%d", vals[i]);
    if (nvals > 0) fputc('\n', f);
    fclose(f);
}

static int
intcmp(const void *a, const void *b)
{
    return *(const int *)a - *(const int *)b;
}

static Node *
new_node(int v)
{
    Node *n = malloc(sizeof *n);
    if (!n) { perror("malloc"); exit(1); }
    n->val = v;
    n->left = n->right = NULL;
    return n;
}

/* Build a balanced BST from sorted vals[lo..hi]. */
static Node *
build(int lo, int hi)
{
    if (lo > hi) return NULL;
    int mid = (lo + hi) / 2;
    Node *n = new_node(vals[mid]);
    n->left  = build(lo, mid - 1);
    n->right = build(mid + 1, hi);
    return n;
}

static void
free_tree(Node *n)
{
    if (!n) return;
    free_tree(n->left);
    free_tree(n->right);
    free(n);
}

/*
 * Print tree rotated 90° counter-clockwise:
 *   right subtree at top, root in middle, left subtree at bottom.
 * Each depth level is indented 4 spaces further right.
 * Reading left-to-right shows root-to-leaf; top-to-bottom is large-to-small.
 */
static void
print_sideways(Node *n, int depth)
{
    if (!n) return;
    print_sideways(n->right, depth + 1);
    printf("%*s%d\n", depth * 4, "", n->val);
    print_sideways(n->left, depth + 1);
}

int
main(int argc, char *argv[])
{
    init_path();
    load();

    if (argc == 1) {
        /* Print mode */
        if (nvals == 0) { puts("(empty)"); return 0; }
        Node *root = build(0, nvals - 1);
        print_sideways(root, 0);
        free_tree(root);

    } else if (argc == 2 && strcmp(argv[1], "reset") == 0) {
        /* Reset mode: clear the state file */
        FILE *f = fopen(state_path, "w");
        if (!f) { perror(state_path); return 1; }
        fclose(f);
        puts("(reset)");

    } else if (argc == 2) {
        /* Insert mode: argument must be an integer */
        const char *arg = argv[1];
        char *end;
        long v = strtol(arg, &end, 10);
        if (end == arg || *end != '\0') {
            fprintf(stderr, "Usage: btree [number|reset]\n");
            return 1;
        }

        int dup = 0;
        for (int i = 0; i < nvals; i++)
            if (vals[i] == v) { dup = 1; break; }

        if (!dup) {
            if (nvals >= MAX_VALS) {
                fputs("error: tree is full\n", stderr);
                return 1;
            }
            vals[nvals++] = v;
            qsort(vals, nvals, sizeof *vals, intcmp);
            save();
        }

        Node *root = build(0, nvals - 1);
        print_sideways(root, 0);
        free_tree(root);

    } else {
        fprintf(stderr, "Usage: btree [number|reset]\n");
        return 1;
    }

    return 0;
}
