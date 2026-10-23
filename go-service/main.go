package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net"
	"net/http"
	"strings"
	"time"
)

const (
	serverAddress = ":8080"
	// pythonAnswerURL = "http://localhost:8000/answer"

	maxRequestBodyBytes  = 1 << 20 // 1 MB
	maxResponseBodyBytes = 2 << 20 // 2 MB
	upstreamTimeout      = 125 * time.Second
)

type AnalyzeRequest struct {
	Message string `json:"message"`
}

type ErrorResponse struct {
	Error string `json:"error"`
}

type PythonAnswerRequest struct {
	Query string `json:"query"`
}

var (
	pythonAnswerURL = "http://localhost:8000/answer"

	upstreamClient = &http.Client{
		Timeout: upstreamTimeout,
	}
)

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", healthHandler)
	mux.HandleFunc("POST /analyze", analyzeHandler)

	server := &http.Server{
		Addr:              serverAddress,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
		IdleTimeout:       60 * time.Second,
		// No WriteTimeout: local LLM responses can take a while.
	}

	log.Printf("Go gateway listening on http://localhost%s", serverAddress)

	if err := server.ListenAndServe(); err != nil &&
		!errors.Is(err, http.ErrServerClosed) {
		log.Fatalf("Go gateway failed: %v", err)
	}
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{
		"status":  "ok",
		"service": "go-gateway",
	})
}

func analyzeHandler(w http.ResponseWriter, r *http.Request) {
	// Reject oversized request bodies before decoding.
	r.Body = http.MaxBytesReader(w, r.Body, maxRequestBodyBytes)

	var request AnalyzeRequest
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()

	if err := decoder.Decode(&request); err != nil {
		var maxBytesError *http.MaxBytesError
		if errors.As(err, &maxBytesError) {
			writeError(w, http.StatusRequestEntityTooLarge,
				"Request body exceeds the 1 MB limit.")
			return
		}

		writeError(w, http.StatusBadRequest,
			"Invalid JSON request body.")
		return
	}

	// Require exactly one JSON value in the request body.
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		writeError(w, http.StatusBadRequest,
			"Request body must contain a single JSON object.")
		return
	}

	request.Message = strings.TrimSpace(request.Message)
	if request.Message == "" {
		writeError(w, http.StatusBadRequest,
			"Field 'message' must not be empty.")
		return
	}

	// Python's /answer endpoint expects a "query" field.
	payload, err := json.Marshal(PythonAnswerRequest{
		Query: request.Message,
	})
	if err != nil {
		log.Printf("Could not encode Python request: %v", err)
		writeError(w, http.StatusInternalServerError,
			"Could not prepare the analysis request.")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), upstreamTimeout)
	defer cancel()

	upstreamRequest, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		pythonAnswerURL,
		bytes.NewReader(payload),
	)
	if err != nil {
		log.Printf("Could not create Python request: %v", err)
		writeError(w, http.StatusInternalServerError,
			"Could not prepare the analysis request.")
		return
	}

	upstreamRequest.Header.Set("Content-Type", "application/json")
	upstreamRequest.Header.Set("Accept", "application/json")

	response, err := upstreamClient.Do(upstreamRequest)
	if err != nil {
		if ctx.Err() == context.DeadlineExceeded ||
			errors.Is(err, context.DeadlineExceeded) {
			writeError(w, http.StatusGatewayTimeout,
				"Python analysis service timed out.")
			return
		}

		var netError net.Error
		if errors.As(err, &netError) && netError.Timeout() {
			writeError(w, http.StatusGatewayTimeout,
				"Python analysis service timed out.")
			return
		}

		log.Printf("Python analysis service request failed: %v", err)
		writeError(w, http.StatusBadGateway,
			"Could not reach the Python analysis service.")
		return
	}
	defer response.Body.Close()

	// Limit how much data the gateway will read from Python.
	body, err := io.ReadAll(
		io.LimitReader(response.Body, maxResponseBodyBytes+1),
	)
	if err != nil {
		log.Printf("Could not read Python response: %v", err)
		writeError(w, http.StatusBadGateway,
			"Could not read the Python analysis response.")
		return
	}

	if len(body) > maxResponseBodyBytes {
		writeError(w, http.StatusBadGateway,
			"Python analysis response exceeded the size limit.")
		return
	}

	contentType := response.Header.Get("Content-Type")
	if contentType != "" {
		w.Header().Set("Content-Type", contentType)
	} else {
		w.Header().Set("Content-Type", "application/json")
	}

	w.WriteHeader(response.StatusCode)
	if _, err := w.Write(body); err != nil {
		log.Printf("Could not write response to client: %v", err)
	}
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, ErrorResponse{Error: message})
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)

	if err := json.NewEncoder(w).Encode(payload); err != nil {
		log.Printf("Could not encode JSON response: %v", err)
	}
}
