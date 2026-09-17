package com.example.backend.query;

import com.example.backend.validation.RequestShape;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record EarthQueryRequest(@NotBlank @Size(max = RequestShape.MAX_QUESTION) String question) {
}
