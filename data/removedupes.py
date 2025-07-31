import csv

def remove_duplicates(input_file, output_file):
    seen = set()
    unique_rows = []

    with open(input_file, 'r', newline='', encoding='utf-8') as infile:
        reader = csv.reader(infile)
        header = next(reader)  # Save the header row
        for row in reader:
            row_tuple = tuple(row)
            if row_tuple not in seen:
                seen.add(row_tuple)
                unique_rows.append(row)

    with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.writer(outfile)
        writer.writerow(header)  # Write the header
        writer.writerows(unique_rows)

    print(f"Removed duplicates. Output saved to '{output_file}'.")

# Example usage
remove_duplicates('enroute.csv', 'enroute_deduped.csv')
