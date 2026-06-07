package main

import "os"

func good() error {
    f, err := os.Open("file.txt")
    if err != nil {
        return err
    }
    defer f.Close()
    return nil
}
