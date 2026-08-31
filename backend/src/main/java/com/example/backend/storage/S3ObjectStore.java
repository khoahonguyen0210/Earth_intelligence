package com.example.backend.storage;

import com.example.backend.tracing.Spans;
import java.util.Optional;
import java.util.function.Supplier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.CreateBucketRequest;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadBucketRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.NoSuchBucketException;
import software.amazon.awssdk.services.s3.model.NoSuchKeyException;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

/**
 * Task 6.4's S3/MinIO implementation. Task 13.3: each operation is an
 * `object_store.<operation>` child span tagged with the bucket and key,
 * the "storage" hop of any trace that reads or writes an object. Task
 * 13.4: every key must pass ObjectKeys.requireSafe first.
 */
@Component
public class S3ObjectStore implements ObjectStore {

    private final S3Client s3Client;
    private final String bucket;
    private final Spans spans;

    public S3ObjectStore(S3Client s3Client, @Value("${object-store.bucket}") String bucket, Spans spans) {
        this.s3Client = s3Client;
        this.bucket = bucket;
        this.spans = spans;
        ensureBucketExists();
    }

    private <T> T traced(String operation, String key, Supplier<T> work) {
        ObjectKeys.requireSafe(key);
        return spans.child("object_store." + operation, () -> {
            spans.tag("object_store.bucket", bucket);
            spans.tag("object_store.key", key);
            return work.get();
        });
    }

    private void ensureBucketExists() {
        try {
            s3Client.headBucket(HeadBucketRequest.builder().bucket(bucket).build());
        } catch (NoSuchBucketException e) {
            s3Client.createBucket(CreateBucketRequest.builder().bucket(bucket).build());
        }
    }

    @Override
    public void put(String key, byte[] content, String contentType) {
        traced("put", key, () -> s3Client.putObject(
                PutObjectRequest.builder().bucket(bucket).key(key).contentType(contentType).build(),
                RequestBody.fromBytes(content)));
    }

    @Override
    public Optional<byte[]> get(String key) {
        return traced("get", key, () -> {
            try {
                byte[] content = s3Client
                        .getObjectAsBytes(GetObjectRequest.builder().bucket(bucket).key(key).build())
                        .asByteArray();

                return Optional.of(content);
            } catch (NoSuchKeyException e) {
                return Optional.empty();
            }
        });
    }

    @Override
    public boolean exists(String key) {
        return traced("exists", key, () -> {
            try {
                s3Client.headObject(HeadObjectRequest.builder().bucket(bucket).key(key).build());

                return true;
            } catch (NoSuchKeyException e) {
                return false;
            }
        });
    }

    @Override
    public void delete(String key) {
        traced("delete", key, () -> s3Client.deleteObject(
                DeleteObjectRequest.builder().bucket(bucket).key(key).build()));
    }
}
