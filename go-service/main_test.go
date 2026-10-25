package main

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestHealthHandler(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()

	healthHandler(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}

	var body map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("invalid JSON response: %v", err)
	}

	if body["status"] != "ok" {
		t.Errorf("expected status 'ok', got %q", body["status"])
	}
	if body["service"] != "go-gateway" {
		t.Errorf("unexpected service name: %q", body["service"])
	}
}

func TestAnalyzeRejectsInvalidRequests(t *testing.T) {
	tests := []struct {
		name string
		body string
		want int
	}{
		{
			name: "empty message",
			body: `{"message":"   "}`,
			want: http.StatusBadRequest,
		},
		{
			name: "malformed JSON",
			body: `{"message":`,
			want: http.StatusBadRequest,
		},
		{
			name: "unknown field",
			body: `{"message":"hello","unexpected":"value"}`,
			want: http.StatusBadRequest,
		},
		{
			name: "multiple JSON values",
			body: `{"message":"hello"} {"message":"again"}`,
			want: http.StatusBadRequest,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(
				http.MethodPost,
				"/analyze",
				strings.NewReader(tc.body),
			)
			rec := httptest.NewRecorder()

			analyzeHandler(rec, req)

			if rec.Code != tc.want {
				t.Fatalf(
					"expected status %d, got %d; body: %s",
					tc.want,
					rec.Code,
					rec.Body.String(),
				)
			}
		})
	}
}

func TestAnalyzeForwardsRequestAndResponse(t *testing.T) {
	mockPython := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodPost {
				t.Errorf("expected POST, got %s", r.Method)
			}
			if r.URL.Path != "/answer" {
				t.Errorf("expected /answer, got %s", r.URL.Path)
			}
			if got := r.Header.Get("Content-Type"); got != "application/json" {
				t.Errorf("unexpected content type: %s", got)
			}

			requestBody, err := io.ReadAll(r.Body)
			if err != nil {
				t.Errorf("could not read request body: %v", err)
				return
			}

			var payload map[string]string
			if err := json.Unmarshal(requestBody, &payload); err != nil {
				t.Errorf("invalid forwarded JSON: %v", err)
				return
			}
			if payload["query"] != "Explain safe mode" {
				t.Errorf("unexpected forwarded query: %q", payload["query"])
			}

			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(
				`{"answer":"Safe mode protects the satellite. [S1]","sources":[{"id":"S1"}]}`,
			))
		},
	))
	defer mockPython.Close()

	originalURL := pythonAnswerURL
	pythonAnswerURL = mockPython.URL + "/answer"
	defer func() {
		pythonAnswerURL = originalURL
	}()

	req := httptest.NewRequest(
		http.MethodPost,
		"/analyze",
		strings.NewReader(`{"message":"  Explain safe mode  "}`),
	)
	rec := httptest.NewRecorder()

	analyzeHandler(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf(
			"expected status 200, got %d; body: %s",
			rec.Code,
			rec.Body.String(),
		)
	}

	if !strings.Contains(rec.Body.String(), `"answer"`) ||
		!strings.Contains(rec.Body.String(), "[S1]") {
		t.Errorf("expected forwarded answer and citation, got: %s", rec.Body.String())
	}
}

func TestAnalyzeHandlesUnavailablePythonService(t *testing.T) {
	mockPython := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {},
	))
	upstreamURL := mockPython.URL
	mockPython.Close() // Close the port so the gateway cannot connect.

	originalURL := pythonAnswerURL
	pythonAnswerURL = upstreamURL
	defer func() {
		pythonAnswerURL = originalURL
	}()

	req := httptest.NewRequest(
		http.MethodPost,
		"/analyze",
		strings.NewReader(`{"message":"Explain safe mode"}`),
	)
	rec := httptest.NewRecorder()

	analyzeHandler(rec, req)

	if rec.Code != http.StatusBadGateway {
		t.Fatalf(
			"expected status 502, got %d; body: %s",
			rec.Code,
			rec.Body.String(),
		)
	}
}

func TestAnalyzeForwardsPythonErrorResponse(t *testing.T) {
	mockPython := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusUnprocessableEntity)
			_, _ = w.Write([]byte(
				`{"detail":"Invalid query"}`,
			))
		},
	))
	defer mockPython.Close()

	originalURL := pythonAnswerURL
	pythonAnswerURL = mockPython.URL + "/answer"
	defer func() {
		pythonAnswerURL = originalURL
	}()

	req := httptest.NewRequest(
		http.MethodPost,
		"/analyze",
		strings.NewReader(`{"message":"Explain safe mode"}`),
	)
	rec := httptest.NewRecorder()

	analyzeHandler(rec, req)

	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("expected status 422, got %d", rec.Code)
	}

	if got := rec.Header().Get("Content-Type"); got != "application/json" {
		t.Errorf("expected application/json, got %q", got)
	}

	if !strings.Contains(rec.Body.String(), "Invalid query") {
		t.Errorf("expected Python error body to be forwarded, got %s",
			rec.Body.String())
	}
}
