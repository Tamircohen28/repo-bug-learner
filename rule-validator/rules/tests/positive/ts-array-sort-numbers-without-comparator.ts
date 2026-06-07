// Positive corpus for ts-array-sort-numbers-without-comparator.

export function f1(durations: number[]) {
  // ruleid: ts-array-sort-numbers-without-comparator
  return durations.sort();
}

export function f2(prices: number[]) {
  // ruleid: ts-array-sort-numbers-without-comparator
  prices.sort();
  return prices;
}

export function f3(amounts: number[]) {
  // ruleid: ts-array-sort-numbers-without-comparator
  return amounts.sort();
}

export function f4(counts: number[]) {
  // ruleid: ts-array-sort-numbers-without-comparator
  const result = counts.sort();
  return result;
}

export function f5(numbers: number[]) {
  // ruleid: ts-array-sort-numbers-without-comparator
  numbers.sort();
}

export function f6(timestamps: number[]) {
  // ruleid: ts-array-sort-numbers-without-comparator
  return timestamps.sort();
}

export function f7(durations: number[]) {
  // Array.from(new Set(...)).sort() pattern
  // ruleid: ts-array-sort-numbers-without-comparator
  return Array.from(new Set(durations)).sort();
}

export function f8(values: number[]) {
  // ruleid: ts-array-sort-numbers-without-comparator
  return Array.from(new Set(values)).sort();
}

export function f9(years: number[]) {
  // ruleid: ts-array-sort-numbers-without-comparator
  years.sort();
}

export function f10(scores: number[]) {
  // ruleid: ts-array-sort-numbers-without-comparator
  return scores.sort();
}

export function f11(sizes: number[]) {
  // ruleid: ts-array-sort-numbers-without-comparator
  sizes.sort();
  return sizes;
}

export function f12(ids: number[]) {
  // ruleid: ts-array-sort-numbers-without-comparator
  return ids.sort();
}
