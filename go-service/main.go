package main

import (
	"bytes"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"time"
)

// AnalyzeRequest is the public request accepted by the Go gateway.
type AnalyzeRequest struct {
	Message string `json:"message"`
}

// ErrorResponse provides consistent JSON errors from the Go gateway.
type ErrorResponse struct {
	Error string `json:"error"`
}

func writeJSONError(w http.ResponseWriter, statusCode int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)

	_ = json.NewEncoder(w).Encode(ErrorResponse{
		Error: message,
	})
}

func main() {
	mux := http.NewServeMux()

	// Local model inference can take longer on a CPU.
	client := &http.Client{
		Timeout: 120 * time.Second,
	}

	// Health check
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		_ = json.NewEncoder(w).Encode(map[string]string{
			"status":  "ok",
			"service": "go-api",
		})
	})

	// Analyze a message using the Python AI service.
	mux.HandleFunc("POST /analyze", func(w http.ResponseWriter, r *http.Request) {
		r.Body = http.MaxBytesReader(w, r.Body, 1<<20) // 1 MB limit
		defer r.Body.Close()

		var request AnalyzeRequest

		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			writeJSONError(w, http.StatusBadRequest, "Invalid JSON request")
			return
		}

		if request.Message == "" {
			writeJSONError(w, http.StatusBadRequest, "message is required")
			return
		}

		// Translate the Go API's "message" field into the Python API's
		// expected "query" field.
		payload := struct {
			Query string `json:"query"`
		}{
			Query: request.Message,
		}

		body, err := json.Marshal(payload)
		if err != nil {
			log.Printf("Failed to encode Python request: %v", err)
			writeJSONError(
				w,
				http.StatusInternalServerError,
				"Failed to encode request",
			)
			return
		}

		pythonURL := "http://localhost:8000/answer"

		pythonRequest, err := http.NewRequestWithContext(
			r.Context(),
			http.MethodPost,
			pythonURL,
			bytes.NewReader(body),
		)
		if err != nil {
			log.Printf("Failed to create Python request: %v", err)
			writeJSONError(
				w,
				http.StatusInternalServerError,
				"Failed to create Python request",
			)
			return
		}

		pythonRequest.Header.Set("Content-Type", "application/json")
		pythonRequest.Header.Set("Accept", "application/json")

		response, err := client.Do(pythonRequest)
		if err != nil {
			log.Printf("Python AI service request failed: %v", err)
			writeJSONError(
				w,
				http.StatusBadGateway,
				"Python AI service unavailable or timed out",
			)
			return
		}
		defer response.Body.Close()

		responseBody, err := io.ReadAll(response.Body)
		if err != nil {
			log.Printf("Failed to read Python response: %v", err)
			writeJSONError(
				w,
				http.StatusBadGateway,
				"Failed to read Python response",
			)
			return
		}

		// Preserve Python's HTTP status and JSON response.
		w.Header().Set(
			"Content-Type",
			response.Header.Get("Content-Type"),
		)
		w.WriteHeader(response.StatusCode)

		if _, err := w.Write(responseBody); err != nil {
			log.Printf("Failed to write response to client: %v", err)
		}
	})

	log.Println("SatelliteOps AI Go API running on :8080")

	if err := http.ListenAndServe(":8080", mux); err != nil {
		log.Fatal(err)
	}
}
