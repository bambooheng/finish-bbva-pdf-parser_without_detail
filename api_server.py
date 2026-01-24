#!/usr/bin/env python
"""
FastAPI server for BBVA PDF Parser
独立FastAPI服务，供决策引擎调用
"""
import os
import sys
import tempfile
import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.pipeline import BankDocumentPipeline
from src.models.schemas import BankDocument, ValidationMetrics
from src.config import config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('api_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title="BBVA PDF Parser API",
    description="高精度BBVA银行对账单PDF解析API服务",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 配置CORS（如果需要跨域访问）
# 生产环境应设置具体的允许源
allowed_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# 全局Pipeline实例（单例模式，避免重复初始化）
_pipeline: Optional[BankDocumentPipeline] = None


def get_pipeline() -> BankDocumentPipeline:
    """获取Pipeline实例（延迟初始化）"""
    global _pipeline
    if _pipeline is None:
        logger.info("Initializing BankDocumentPipeline...")
        config_path = os.getenv('CONFIG_PATH', 'config.yaml')
        _pipeline = BankDocumentPipeline(config_path=config_path)
        logger.info("BankDocumentPipeline initialized successfully")
    return _pipeline


# ==================== 请求/响应模型 ====================

class ParseRequest(BaseModel):
    """解析请求模型（使用文件路径）"""
    pdf_path: str = Field(..., description="PDF文件路径")
    validate: bool = Field(True, description="是否启用验证")
    output_dir: Optional[str] = Field(None, description="输出目录（可选）")
    simplified_output: bool = Field(True, description="是否使用简化输出（仅业务数据+页码，默认True）")
    external_transactions: Optional[Dict[str, Any]] = Field(None, description="外部流水明细数据（可选）")


class ParseResponse(BaseModel):
    """解析响应模型"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    data: Optional[dict] = Field(None, description="解析结果数据")
    metadata: Optional[dict] = Field(None, description="元数据摘要")
    error: Optional[str] = Field(None, description="错误信息（如果失败）")
    processing_time: Optional[float] = Field(None, description="处理时间（秒）")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(..., description="服务状态")
    service: str = Field(..., description="服务名称")
    version: str = Field(..., description="API版本")
    timestamp: str = Field(..., description="时间戳")
    config: Optional[dict] = Field(None, description="配置信息")


class BatchParseRequest(BaseModel):
    """批量解析请求"""
    pdf_paths: List[str] = Field(..., description="PDF文件路径列表")
    validate: bool = Field(True, description="是否启用验证")


class BatchParseResponse(BaseModel):
    """批量解析响应"""
    success: bool
    total: int
    succeeded: int
    failed: int
    results: List[dict]


# ==================== API端点 ====================

@app.get("/", tags=["Info"])
async def root():
    """根端点"""
    return {
        "service": "BBVA PDF Parser API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    健康检查端点
    
    返回服务状态和配置信息
    """
    try:
        # 尝试初始化pipeline（如果未初始化）
        pipeline = get_pipeline()
        
        # 检查配置
        config_info = {
            "llm_provider": config.get('llm.provider', 'unknown'),
            "ocr_engine": config.get('ocr.primary_engine', 'unknown'),
            "validation_enabled": config.get('validation.enable_pdf_rebuild', False)
        }
        
        return HealthResponse(
            status="healthy",
            service="bbva-pdf-parser",
            version="1.0.0",
            timestamp=datetime.now().isoformat(),
            config=config_info
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            service="bbva-pdf-parser",
            version="1.0.0",
            timestamp=datetime.now().isoformat(),
            config=None
        )


@app.post("/parse", response_model=ParseResponse, tags=["Parse"])
async def parse_pdf_upload(
    file: UploadFile = File(..., description="PDF文件"),
    validate: bool = Form(True, description="是否启用验证"),
    output_dir: Optional[str] = Form(None, description="输出目录")
):
    """
    解析PDF文档（文件上传方式）
    
    - **file**: PDF文件（multipart/form-data）
    - **validate**: 是否启用验证（默认：true）
    - **output_dir**: 输出目录（可选）
    
    返回：
    - 成功时返回完整的结构化数据
    - 失败时返回错误信息
    """
    start_time = datetime.now()
    temp_file_path = None
    
    try:
        # 验证文件类型
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=400,
                detail="文件必须是PDF格式"
            )
        
        # 保存上传的文件到临时目录
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            temp_file_path = tmp_file.name
        
        logger.info(f"Received PDF file: {file.filename}, size: {len(content)} bytes")
        
        # 获取Pipeline实例
        pipeline = get_pipeline()
        
        # 处理PDF
        document = pipeline.process_pdf(
            pdf_path=temp_file_path,
            output_dir=output_dir,
            validate=validate,
            simplified_output=True  # API默认使用简化输出
        )
        
        # 计算处理时间
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # 构建响应
        result_dict = document.dict()
        
        # 提取关键元数据
        metadata = {
            "document_type": document.metadata.document_type,
            "bank": document.metadata.bank,
            "account_number": document.metadata.account_number,
            "total_pages": document.metadata.total_pages,
            "transactions_count": len(document.structured_data.account_summary.transactions),
            "extraction_completeness": document.validation_metrics.extraction_completeness,
            "content_accuracy": document.validation_metrics.content_accuracy,
            "has_discrepancies": len(document.validation_metrics.discrepancy_report) > 0
        }
        
        logger.info(f"PDF parsed successfully: {metadata}")
        
        return ParseResponse(
            success=True,
            message="PDF解析成功",
            data=result_dict,
            metadata=metadata,
            processing_time=processing_time
        )
    
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        raise HTTPException(status_code=404, detail=f"文件未找到: {str(e)}")
    
    except ValueError as e:
        logger.error(f"Invalid input: {e}")
        raise HTTPException(status_code=400, detail=f"无效输入: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error parsing PDF: {e}", exc_info=True)
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return ParseResponse(
            success=False,
            message="PDF解析失败",
            error=f"{type(e).__name__}: {str(e)}",
            processing_time=processing_time
        )
    
    finally:
        # 清理临时文件
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file: {e}")


@app.post("/parse/path", response_model=ParseResponse, tags=["Parse"])
async def parse_pdf_path(
    request: ParseRequest
):
    """
    解析PDF文档（文件路径方式）
    
    - **pdf_path**: PDF文件路径
    - **validate**: 是否启用验证
    - **output_dir**: 输出目录（可选）
    
    返回：
    - 成功时返回完整的结构化数据
    - 失败时返回错误信息
    """
    start_time = datetime.now()
    
    try:
        # 验证文件存在
        if not os.path.exists(request.pdf_path):
            raise HTTPException(
                status_code=404,
                detail=f"文件不存在: {request.pdf_path}"
            )
        
        # 验证文件类型
        if not request.pdf_path.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=400,
                detail="文件必须是PDF格式"
            )
        
        logger.info(f"Parsing PDF from path: {request.pdf_path}")
        
        # 获取Pipeline实例
        pipeline = get_pipeline()
        
        # 处理PDF
        document = pipeline.process_pdf(
            pdf_path=request.pdf_path,
            output_dir=request.output_dir,
            validate=request.validate,
            simplified_output=request.simplified_output,  # 使用请求中的参数
            external_transactions_data=request.external_transactions  # 外部交易数据
        )
        
        # 计算处理时间
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # 构建响应
        result_dict = document.dict()
        
        # 提取关键元数据
        metadata = {
            "document_type": document.metadata.document_type,
            "bank": document.metadata.bank,
            "account_number": document.metadata.account_number,
            "total_pages": document.metadata.total_pages,
            "transactions_count": len(document.structured_data.account_summary.transactions),
            "extraction_completeness": document.validation_metrics.extraction_completeness,
            "content_accuracy": document.validation_metrics.content_accuracy,
            "has_discrepancies": len(document.validation_metrics.discrepancy_report) > 0
        }
        
        logger.info(f"PDF parsed successfully: {metadata}")
        
        return ParseResponse(
            success=True,
            message="PDF解析成功",
            data=result_dict,
            metadata=metadata,
            processing_time=processing_time
        )
    
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"文件未找到: {request.pdf_path}")
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"无效输入: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error parsing PDF: {e}", exc_info=True)
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return ParseResponse(
            success=False,
            message="PDF解析失败",
            error=f"{type(e).__name__}: {str(e)}",
            processing_time=processing_time
        )


@app.post("/parse/batch", response_model=BatchParseResponse, tags=["Parse"])
async def parse_pdf_batch(
    request: BatchParseRequest
):
    """
    批量解析PDF文档
    
    - **pdf_paths**: PDF文件路径列表
    - **validate**: 是否启用验证
    
    返回：
    - 批量处理结果汇总
    """
    logger.info(f"Batch parsing {len(request.pdf_paths)} PDF files")
    
    results = []
    succeeded = 0
    failed = 0
    
    pipeline = get_pipeline()
    
    for pdf_path in request.pdf_paths:
        try:
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"文件不存在: {pdf_path}")
            
            start_time = datetime.now()
            document = pipeline.process_pdf(
                pdf_path=pdf_path,
                output_dir=None,
                validate=request.validate
            )
            processing_time = (datetime.now() - start_time).total_seconds()
            
            results.append({
                "pdf_path": pdf_path,
                "success": True,
                "metadata": {
                    "document_type": document.metadata.document_type,
                    "bank": document.metadata.bank,
                    "transactions_count": len(document.structured_data.account_summary.transactions),
                    "extraction_completeness": document.validation_metrics.extraction_completeness
                },
                "processing_time": processing_time
            })
            succeeded += 1
        
        except Exception as e:
            logger.error(f"Failed to parse {pdf_path}: {e}")
            results.append({
                "pdf_path": pdf_path,
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            })
            failed += 1
    
    return BatchParseResponse(
        success=failed == 0,
        total=len(request.pdf_paths),
        succeeded=succeeded,
        failed=failed,
        results=results
    )


@app.get("/transactions", tags=["Data"])
async def extract_transactions(
    pdf_path: str = Query(..., description="PDF文件路径"),
    validate: bool = Query(True, description="是否启用验证")
):
    """
    提取交易数据（简化接口，只返回交易信息）
    
    - **pdf_path**: PDF文件路径
    - **validate**: 是否启用验证
    
    返回：
    - 交易列表和相关统计
    """
    try:
        if not os.path.exists(pdf_path):
            raise HTTPException(status_code=404, detail="文件不存在")
        
        pipeline = get_pipeline()
        document = pipeline.process_pdf(
            pdf_path=pdf_path,
            output_dir=None,
            validate=validate
        )
        
        transactions = document.structured_data.account_summary.transactions
        
        return {
            "success": True,
            "account_summary": {
                "initial_balance": str(document.structured_data.account_summary.initial_balance) if document.structured_data.account_summary.initial_balance else None,
                "final_balance": str(document.structured_data.account_summary.final_balance) if document.structured_data.account_summary.final_balance else None,
                "deposits": str(document.structured_data.account_summary.deposits) if document.structured_data.account_summary.deposits else None,
                "withdrawals": str(document.structured_data.account_summary.withdrawals) if document.structured_data.account_summary.withdrawals else None,
            },
            "transactions": [
                {
                    "date": t.date.isoformat() if t.date else None,
                    "description": t.description,
                    "amount": str(t.amount),
                    "balance": str(t.balance) if t.balance else None,
                    "reference": t.reference
                }
                for t in transactions
            ],
            "total_transactions": len(transactions),
            "metadata": {
                "account_number": document.metadata.account_number,
                "period": document.metadata.period,
                "extraction_completeness": document.validation_metrics.extraction_completeness
            }
        }
    
    except Exception as e:
        logger.error(f"Error extracting transactions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 异常处理 ====================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "内部服务器错误",
            "detail": str(exc)
        }
    )


# ==================== 启动配置 ====================

if __name__ == "__main__":
    # 从环境变量读取配置
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    workers = int(os.getenv("API_WORKERS", "4"))
    log_level = os.getenv("LOG_LEVEL", "info")
    
    logger.info(f"Starting BBVA PDF Parser API server")
    logger.info(f"Host: {host}, Port: {port}, Workers: {workers}")
    
    # 使用uvicorn运行（开发环境）
    # 生产环境建议使用: uvicorn api_server:app --host 0.0.0.0 --port 8000 --workers 4
    uvicorn.run(
        "api_server:app",
        host=host,
        port=port,
        workers=workers if os.getenv("ENV") != "development" else 1,
        log_level=log_level,
        reload=os.getenv("ENV") == "development"
    )

