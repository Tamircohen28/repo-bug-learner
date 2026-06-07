package main

import "os"

func good(path string) {
    f, err := os.Open(path)
    if err != nil {
        return
    }
    defer f.Close()
}
