package main

import "os"

func bad() {
    f, _ := os.Open("missing.txt")
    _ = f
}
