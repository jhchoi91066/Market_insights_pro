# -*- coding: utf-8 -*-
"""
이 파일은 데이터베이스 연결 및 CRUD(Create, Read, Update, Delete) 작업을 처리합니다.
psycopg2-binary 라이브러리가 필요합니다. (pip install psycopg2-binary)
"""
import os
import psycopg2

# 데이터베이스 연결 정보 (환경 변수 사용을 권장)
DB_NAME = "market_insights"
DB_USER = "user" # 실제 사용자 이름으로 변경 필요
DB_PASSWORD = "password" # 실제 비밀번호로 변경 필요
DB_HOST = "localhost"
DB_PORT = "5432"

def get_db_connection():
    """
    데이터베이스에 연결하고 connection 객체를 반환합니다.
    """
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        return conn
    except psycopg2.OperationalError as e:
        print(f"데이터베이스 연결 오류: {e}")
        return None

def insert_product(product_data):
    """
    'products' 테이블에 새로운 상품 데이터를 삽입합니다.
    (구현 예정)
    :param product_data: 상품 정보를 담은 딕셔너리
    """
    print(f"상품 추가: {product_data.get('name')}")
    # conn = get_db_connection()
    # ... (cursor 생성 및 INSERT 구문 실행)
    pass

def get_product_by_id(product_id):
    """
    'products' 테이블에서 product_id로 상품을 조회합니다.
    (구현 예정)
    :param product_id: 조회할 상품의 ID
    :return: 상품 정보 딕셔너리
    """
    print(f"상품 조회: {product_id}")
    # conn = get_db_connection()
    # ... (cursor 생성 및 SELECT 구문 실행)
    return None

def update_product_price(product_id, new_price):
    """
    'products' 테이블의 상품 가격을 업데이트합니다.
    (구현 예정)
    :param product_id: 수정할 상품의 ID
    :param new_price: 새로운 가격
    """
    print(f"상품 가격 수정: {product_id} -> ${new_price}")
    # conn = get_db_connection()
    # ... (cursor 생성 및 UPDATE 구문 실행)
    pass

def delete_product(product_id):
    """
    'products' 테이블에서 상품을 삭제합니다.
    (구현 예정)
    :param product_id: 삭제할 상품의 ID
    """
    print(f"상품 삭제: {product_id}")
    # conn = get_db_connection()
    # ... (cursor 생성 및 DELETE 구문 실행)
    pass

if __name__ == '__main__':
    print("데이터베이스 연결 테스트...")
    connection = get_db_connection()
    if connection:
        print("데이터베이스 연결 성공!")
        connection.close()
        print("데이터베이스 연결 종료.")
        
        # 함수 테스트 호출
        print("\nCRUD 함수 테스트 호출:")
        insert_product({'name': 'Test Product', 'product_id': 'T001'})
        get_product_by_id('T001')
        update_product_price('T001', 99.99)
        delete_product('T001')
    else:
        print("데이터베이스 연결에 실패했습니다.")
