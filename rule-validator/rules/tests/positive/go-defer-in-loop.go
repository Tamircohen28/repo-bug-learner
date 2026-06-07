package main

import "os"

func bad() {
    for _, path := range []string{"a", "b"} {
        f, _ := os.Open(path)
        defer f.Close()
    }
}
