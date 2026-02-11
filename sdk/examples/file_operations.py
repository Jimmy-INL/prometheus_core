"""File upload/download example for the storage client library."""

from storage_client import StorageClient, ConnectionConfig, ItemCreate, RelationshipCreate
from pathlib import Path
import tempfile
import shutil


def main():
    # Configure connection from .env file
    config = ConnectionConfig.from_env()

    with StorageClient(config) as client:
        print("=== Creating a test file ===")
        # Create a temporary test file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            test_file = Path(f.name)
            f.write("id,name,value\n")
            f.write("1,Test A,100\n")
            f.write("2,Test B,200\n")
            f.write("3,Test C,300\n")

        print(f"Created test file: {test_file}")

        print("\n=== Uploading file ===")
        file_meta = client.files.upload(
            test_file,
            name="example_data.csv",
            description="Example CSV data file"
        )
        print(f"Uploaded file: {file_meta.name}")
        print(f"File ID: {file_meta.id}")
        print(f"File size: {file_meta.size} bytes")
        print(f"File type: {file_meta.file_type}")

        print("\n=== Creating item and linking file ===")
        item = client.items.create(ItemCreate(
            name="Data Analysis Project",
            description="Project with attached data file",
            properties={
                "project_type": "analysis",
                "data_source": "experimental",
                "_example_script": True
            }
        ))
        print(f"Created item: {item.name} (ID: {item.id})")

        # Create relationship between item and file
        rel = client.relationships.create(RelationshipCreate(
            from_item_id=item.id,
            to_item_id=file_meta.id,
            relationship_type="has_data_file"
        ))
        print(f"Linked file to item")

        print("\n=== Downloading file ===")
        download_path = Path(tempfile.gettempdir()) / "downloaded_example.csv"
        client.files.download(file_meta.id, download_path)
        print(f"Downloaded to: {download_path}")

        # Verify download
        with open(download_path, 'r') as f:
            content = f.read()
            print(f"File content preview:\n{content[:100]}...")

        print("\n=== Large file upload (chunked) ===")
        # Create a larger test file
        large_file = Path(tempfile.gettempdir()) / "large_test.dat"
        with open(large_file, 'wb') as f:
            # Write 10MB of data
            chunk = b'0' * (1024 * 1024)  # 1MB
            for _ in range(10):
                f.write(chunk)

        print(f"Created large file: {large_file.stat().st_size / (1024*1024):.1f} MB")

        # Upload in chunks
        large_file_meta = client.files.upload_chunked(
            large_file,
            chunk_size=2 * 1024 * 1024,  # 2MB chunks
            description="Large test file"
        )
        print(f"Uploaded large file: {large_file_meta.name} (ID: {large_file_meta.id})")

        print("\n=== Cleanup ===")
        # Clean up test files
        test_file.unlink()
        download_path.unlink()
        large_file.unlink()
        print("Cleaned up temporary files")

        print("\nFile operations example completed successfully!")


if __name__ == "__main__":
    main()
