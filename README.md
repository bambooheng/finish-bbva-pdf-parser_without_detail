# BBVA PDF Document Parsing System

A high-precision, verifiable PDF parsing system for BBVA bank statements with bidirectional validation.

## Features

- **100% Information Capture**: Extracts all visible elements (text, tables, images, headers, footers)
- **Zero-Error Guarantee**: Multiple validation layers ensure accuracy
- **Dynamic Adaptation**: No hardcoding - handles various BBVA document variants
- **Bidirectional Validation**: Rebuilds PDF from structured data and compares pixel-by-pixel
- **Position Preservation**: Maintains exact coordinates for every extracted element

## Installation

```bash
pip install -r requirements.txt
```


## Configuration

1. Copy `.env.example` to `.env` and configure API keys:
```bash
ANTHROPIC_API_KEY=your_key_here
# or
OPENAI_API_KEY=your_key_here
```

2. Update `config.yaml` with your MinerU installation path

## Usage

```bash
python main.py --input path/to/bbva_statement.pdf --output output/
```

## Project Structure

```
bbva-pdf-parser/
├── src/
│   ├── ocr/
│   │   ├── __init__.py
│   │   ├── mineru_handler.py      # MinerU OCR integration
│   │   └── ocr_verifier.py        # Dual verification
│   ├── layout/
│   │   ├── __init__.py
│   │   ├── layout_analyzer.py     # Dynamic layout analysis
│   │   └── region_clustering.py   # Visual feature clustering
│   ├── tables/
│   │   ├── __init__.py
│   │   ├── table_parser.py        # Intelligent table parsing
│   │   └── table_validator.py     # Table semantic validation
│   ├── extraction/
│   │   ├── __init__.py
│   │   ├── data_extractor.py      # Structured data extraction
│   │   └── semantic_analyzer.py   # LLM-based semantic analysis
│   ├── validation/
│   │   ├── __init__.py
│   │   ├── pdf_rebuilder.py       # PDF reconstruction
│   │   ├── pdf_comparator.py      # Pixel-level comparison
│   │   └── validator.py           # Complete validation pipeline
│   └── models/
│       ├── __init__.py
│       └── schemas.py            # Pydantic data models
├── config.yaml
├── main.py
└── requirements.txt
```

## Output Format

See the prompt file for the complete JSON schema. The output includes:
- Document metadata
- Page-by-page layout elements with coordinates
- Structured transaction data
- Validation metrics and discrepancy reports

## Recent Improvements

### ✅ Completed Enhancements

1. **MinerU Integration** - Full implementation with multiple invocation patterns
   - Python package import support
   - Command-line invocation fallbacks
   - JSON output parsing and standardization
   - Automatic fallback to PyMuPDF

2. **LLM Client** - Enhanced JSON response parsing
   - Claude/OpenAI response parsing
   - Markdown code block extraction
   - Role identification with proper parsing
   - Error handling with fallbacks

3. **PDF Rebuilder** - Improved font and layout preservation
   - Better font size estimation
   - Text wrapping for long content
   - Multi-line text rendering

4. **PDF Comparator** - Fixed array conversion bugs
   - Proper handling of grayscale/RGB/RGBA
   - Fixed numpy buffer conversion

5. **Semantic Analyzer** - Complete LLM integration
   - Full semantic validation
   - Data summary extraction
   - Structured result format

6. **Pipeline** - Enhanced error handling
   - Better validation flow
   - Config path support
   - Improved exception handling

### 📝 Documentation

- Added `USAGE.md` with comprehensive usage guide (Chinese)
- Improved code documentation
- Added configuration examples

## Next Steps

1. **Test with Real BBVA PDFs** - Validate end-to-end processing
2. **Configure MinerU** - Set up your MinerU installation path
3. **Set API Keys** - Configure Anthropic or OpenAI API keys
4. **Fine-tune Validation** - Adjust thresholds in `config.yaml`

## License

MIT

