다음은 제공된 "쇼핑인사이트 API 레퍼런스" 문서를 하나의 마크다운(MD) 파일로 정리한 내용입니다.

-----

# 쇼핑인사이트 API 레퍼런스 📃

네이버 쇼핑인사이트 API는 네이버 통합검색의 쇼핑 영역과 네이버쇼핑에서의 검색 클릭 추이를 조회할 수 있는 기능을 제공합니다. 데이터는 **JSON 형식**으로 반환됩니다.

## API 목록

  * [쇼핑인사이트 분야별 트렌드 조회](https://www.google.com/search?q=%23%EC%87%BC%ED%95%91%EC%9D%B8%EC%82%AC%EC%9D%B4%ED%8A%B8-%EB%B6%84%EC%95%BC%EB%B3%84-%ED%8A%B8%EB%A0%8C%EB%93%9C-%EC%A1%B0%ED%9A%8C)
  * [쇼핑인사이트 분야 내 기기별 트렌드 조회](https://www.google.com/search?q=%23%EC%87%BC%ED%95%91%EC%9D%B8%EC%82%AC%EC%9D%B4%ED%8A%B8-%EB%B6%84%EC%95%BC-%EB%82%B4-%EA%B8%B0%EA%B8%B0%EB%B3%84-%ED%8A%B8%EB%A0%8C%EB%93%9C-%EC%A1%B0%ED%9A%8C)
  * [쇼핑인사이트 분야 내 성별 트렌드 조회](https://www.google.com/search?q=%23%EC%87%BC%ED%95%91%EC%9D%B8%EC%82%AC%EC%9D%B4%ED%8A%B8-%EB%B6%84%EC%95%BC-%EB%82%B4-%EC%84%B1%EB%B3%84-%ED%8A%B8%EB%A0%8C%EB%93%9C-%EC%A1%B0%ED%9A%8C)
  * [쇼핑인사이트 분야 내 연령별 트렌드 조회](https://www.google.com/search?q=%23%EC%87%BC%ED%95%91%EC%9D%B8%EC%82%AC%EC%9D%B4%ED%8A%B8-%EB%B6%84%EC%95%BC-%EB%82%B4-%EC%97%B0%EB%A0%B9%EB%B3%84-%ED%8A%B8%EB%A0%8C%EB%93%9C-%EC%A1%B0%ED%9A%8C)
  * [쇼핑인사이트 키워드별 트렌드 조회](https://www.google.com/search?q=%23%EC%87%BC%ED%95%91%EC%9D%B8%EC%82%AC%EC%9D%B4%ED%8A%B8-%ED%82%A4%EC%9B%8C%EB%93%9C%EB%B3%84-%ED%8A%B8%EB%A0%8C%EB%93%9C-%EC%A1%B0%ED%9A%8C)
  * [쇼핑인사이트 키워드 기기별 트렌드 조회](https://www.google.com/search?q=%23%EC%87%BC%ED%95%91%EC%9D%B8%EC%82%AC%EC%9D%B4%ED%8A%B8-%ED%82%A4%EC%9B%8C%EB%93%9C-%EA%B8%B0%EA%B8%B0%EB%B3%84-%ED%8A%B8%EB%A0%8C%EB%93%9C-%EC%A1%B0%ED%9A%8C)
  * [쇼핑인사이트 키워드 성별 트렌드 조회](https://www.google.com/search?q=%23%EC%87%BC%ED%95%91%EC%9D%B8%EC%82%AC%EC%9D%B4%ED%8A%B8-%ED%82%A4%EC%9B%8C%EB%93%9C-%EC%84%B1%EB%B3%84-%ED%8A%B8%EB%A0%8C%EB%93%9C-%EC%A1%B0%ED%9A%8C)
  * [쇼핑인사이트 키워드 연령별 트렌드 조회](https://www.google.com/search?q=%23%EC%87%BC%ED%95%91%EC%9D%B8%EC%82%AC%EC%9D%B4%ED%8A%B8-%ED%82%A4%EC%9B%8C%EB%93%9C-%EC%97%B0%EB%A0%B9%EB%B3%84-%ED%8A%B8%EB%A0%8C%EB%93%9C-%EC%A1%B0%ED%9A%8C)
  * [오류 코드](https://www.google.com/search?q=%23%EC%98%A4%EB%A5%98-%EC%BD%94%EB%93%9C)
  * [구현 예제](https://www.google.com/search?q=%23%EC%87%BC%ED%95%91%EC%9D%B8%EC%82%AC%EC%9D%B4%ED%8A%B8-api-%EA%B5%AC%ED%98%84-%EC%98%88%EC%A0%9C)

-----

## 쇼핑인사이트 분야별 트렌드 조회

### 설명

네이버 통합검색의 쇼핑 영역과 네이버쇼핑에서의 검색 클릭 추이를 **쇼핑 분야별**로 조회한 데이터를 JSON 형식으로 반환합니다.

  * **요청 URL:** `https://openapi.naver.com/v1/datalab/shopping/categories`
  * **프로토콜:** `HTTPS`
  * **HTTP 메서드:** `POST`

### 파라미터

| 파라미터 | 타입 | 필수 여부 | 설명 |
| :--- | :--- | :--- | :--- |
| `startDate` | string | Y | 조회 기간 시작 날짜 (yyyy-mm-dd 형식, 2017-08-01부터) |
| `endDate` | string | Y | 조회 기간 종료 날짜 (yyyy-mm-dd 형식) |
| `timeUnit` | string | Y | 구간 단위 (`date`: 일간, `week`: 주간, `month`: 월간) |
| `category` | array(JSON) | Y | 분야 이름과 코드 쌍의 배열 (최대 3개) |
| `category.name`| string | Y | 쇼핑 분야 이름 |
| `category.param`| array(string) | Y | 쇼핑 분야 코드 (`cat_id` 파라미터 값) |
| `device` | string | N | 기기 (`pc`, `mo`) |
| `gender` | string | N | 성별 (`m`: 남성, `f`: 여성) |
| `ages` | array(JSON) | N | 연령 (`10` \~ `60`) |

### 요청 예

```bash
curl "https://openapi.naver.com/v1/datalab/shopping/categories" \
--header "X-Naver-Client-Id: {클라이언트 아이디}" \
--header "X-Naver-Client-Secret: {클라이언트 시크릿}" \
--header "Content-Type: application/json" \
-d '{
  "startDate": "2017-08-01",
  "endDate": "2017-09-30",
  "timeUnit": "month",
  "category": [
      {"name": "패션의류", "param": [ "50000000"]},
      {"name": "화장품/미용", "param": [ "50000002"]}
  ],
  "device": "pc",
  "gender": "f",
  "ages": [ "20",  "30"]
}'
```

### 응답

| 속성 | 타입 | 설명 |
| :--- | :--- | :--- |
| `startDate` | string | 조회 기간 시작 날짜 |
| `endDate` | string | 조회 기간 종료 날짜 |
| `timeUnit` | string | 구간 단위 |
| `results.title` | string | 쇼핑 분야 이름 |
| `results.category`| string | 쇼핑 분야 코드 |
| `results.data.period`| string | 구간별 시작 날짜 |
| `results.data.ratio`| number | 구간별 클릭량의 상대적 비율 (최대값 100) |

### 응답 예

```json
{
  "startDate": "2017-08-01",
  "endDate": "2017-09-30",
  "timeUnit": "month",
  "results": [
    {
      "title": "패션의류",
      "category": ["50000000"],
      "data": [{"period": "2017-08-01", "ratio": 84.01252}, {"period": "2017-09-01", "ratio": 100}]
    },
    {
      "title": "화장품/미용",
      "category": ["50000002"],
      "data": [{"period": "2017-08-01", "ratio": 22.21162}, {"period": "2017-09-01", "ratio": 21.54278}]
    }
  ]
}
```

-----

## 쇼핑인사이트 분야 내 기기별 트렌드 조회

### 설명

특정 쇼핑 분야의 검색 클릭 추이를 \*\*기기별(PC, 모바일)\*\*로 조회합니다.

  * **요청 URL:** `https://openapi.naver.com/v1/datalab/shopping/category/device`
  * **프로토콜:** `HTTPS`
  * **HTTP 메서드:** `POST`

### 파라미터

| 파라미터 | 타입 | 필수 여부 | 설명 |
| :--- | :--- | :--- | :--- |
| `startDate` | string | Y | 조회 기간 시작 날짜 (yyyy-mm-dd 형식) |
| `endDate` | string | Y | 조회 기간 종료 날짜 (yyyy-mm-dd 형식) |
| `timeUnit` | string | Y | 구간 단위 (`date`, `week`, `month`) |
| `category` | string | Y | 쇼핑 분야 코드 |
| `device` | string | N | 기기 (`pc`, `mo`) |
| `gender` | string | N | 성별 (`m`, `f`) |
| `ages` | array(JSON) | N | 연령 (`10` \~ `60`) |

### 응답

| 속성 | 타입 | 설명 |
| :--- | :--- | :--- |
| ... | ... | (공통 속성은 위와 동일) |
| `results.data.group` | string | 기기 (`pc`, `mo`) |
| `results.data.ratio` | number | 구간별 클릭량의 상대적 비율 |

-----

## 쇼핑인사이트 분야 내 성별 트렌드 조회

### 설명

특정 쇼핑 분야의 검색 클릭 추이를 **성별**로 조회합니다.

  * **요청 URL:** `https://openapi.naver.com/v1/datalab/shopping/category/gender`
  * **프로토콜:** `HTTPS`
  * **HTTP 메서드:** `POST`

### 파라미터

| 파라미터 | 타입 | 필수 여부 | 설명 |
| :--- | :--- | :--- | :--- |
| `startDate` | string | Y | 조회 기간 시작 날짜 (yyyy-mm-dd 형식) |
| `endDate` | string | Y | 조회 기간 종료 날짜 (yyyy-mm-dd 형식) |
| `timeUnit` | string | Y | 구간 단위 (`date`, `week`, `month`) |
| `category` | string | Y | 쇼핑 분야 코드 |
| `device` | string | N | 기기 (`pc`, `mo`) |
| `gender` | string | N | 성별 (`m`, `f`) |
| `ages` | array(JSON) | N | 연령 (`10` \~ `60`) |

### 응답

| 속성 | 타입 | 설명 |
| :--- | :--- | :--- |
| ... | ... | (공통 속성은 위와 동일) |
| `results.data.group` | string | 성별 (`m`, `f`) |
| `results.data.ratio` | number | 구간별 클릭량의 상대적 비율 |

-----

## 쇼핑인사이트 분야 내 연령별 트렌드 조회

### 설명

특정 쇼핑 분야의 검색 클릭 추이를 **연령별**로 조회합니다.

  * **요청 URL:** `https://openapi.naver.com/v1/datalab/shopping/category/age`
  * **프로토콜:** `HTTPS`
  * **HTTP 메서드:** `POST`

### 파라미터

| 파라미터 | 타입 | 필수 여부 | 설명 |
| :--- | :--- | :--- | :--- |
| `startDate` | string | Y | 조회 기간 시작 날짜 (yyyy-mm-dd 형식) |
| `endDate` | string | Y | 조회 기간 종료 날짜 (yyyy-mm-dd 형식) |
| `timeUnit` | string | Y | 구간 단위 (`date`, `week`, `month`) |
| `category` | string | Y | 쇼핑 분야 코드 |
| `device` | string | N | 기기 (`pc`, `mo`) |
| `gender` | string | N | 성별 (`m`, `f`) |
| `ages` | array(JSON)| N | 연령 (`10` \~ `60`) |

### 응답

| 속성 | 타입 | 설명 |
| :--- | :--- | :--- |
| ... | ... | (공통 속성은 위와 동일) |
| `results.data.group`| string | 연령 (`10` \~ `60`) |
| `results.data.ratio`| number | 구간별 클릭량의 상대적 비율 |

-----

## 쇼핑인사이트 키워드별 트렌드 조회

### 설명

특정 쇼핑 분야의 검색 클릭 추이를 **검색 키워드별**로 조회합니다.

  * **요청 URL:** `https://openapi.naver.com/v1/datalab/shopping/category/keywords`
  * **프로토콜:** `HTTPS`
  * **HTTP 메서드:** `POST`

### 파라미터

| 파라미터 | 타입 | 필수 여부 | 설명 |
| :--- | :--- | :--- | :--- |
| `startDate` | string | Y | 조회 기간 시작 날짜 (yyyy-mm-dd 형식) |
| `endDate` | string | Y | 조회 기간 종료 날짜 (yyyy-mm-dd 형식) |
| `timeUnit` | string | Y | 구간 단위 (`date`, `week`, `month`) |
| `category` | string | Y | 쇼핑 분야 코드 |
| `keyword` | array(JSON) | Y | 검색 키워드 그룹 이름과 키워드 쌍의 배열 (최대 5개) |
| `keyword.name`| string | Y | 검색 키워드 그룹 이름 |
| `keyword.param`| array(string)| Y | 비교할 검색어 (1개만 설정) |
| `device` | string | N | 기기 (`pc`, `mo`) |
| `gender` | string | N | 성별 (`m`, `f`) |
| `ages` | array(JSON)| N | 연령 (`10` \~ `60`) |

### 응답

| 속성 | 타입 | 설명 |
| :--- | :--- | :--- |
| ... | ... | (공통 속성은 위와 동일) |
| `results.title` | string | 검색 키워드 그룹 이름 |
| `results.keyword` | array(string)| 검색 키워드 |
| `results.data.ratio`| number | 구간별 클릭량의 상대적 비율 |

-----

## 쇼핑인사이트 키워드 기기별 트렌드 조회

### 설명

특정 쇼핑 분야와 검색 키워드의 검색 클릭 추이를 \*\*기기별(PC, 모바일)\*\*로 조회합니다.

  * **요청 URL:** `https://openapi.naver.com/v1/datalab/shopping/category/keyword/device`
  * **프로토콜:** `HTTPS`
  * **HTTP 메서드:** `POST`

### 파라미터

| 파라미터 | 타입 | 필수 여부 | 설명 |
| :--- | :--- | :--- | :--- |
| `startDate` | string | Y | 조회 기간 시작 날짜 (yyyy-mm-dd 형식) |
| `endDate` | string | Y | 조회 기간 종료 날짜 (yyyy-mm-dd 형식) |
| `timeUnit` | string | Y | 구간 단위 (`date`, `week`, `month`) |
| `category` | string | Y | 쇼핑 분야 코드 |
| `keyword` | string | Y | 검색 키워드 |
| `device` | string | N | 기기 (`pc`, `mo`) |
| `gender` | string | N | 성별 (`m`, `f`) |
| `ages` | array(JSON)| N | 연령 (`10` \~ `60`) |

### 응답

| 속성 | 타입 | 설명 |
| :--- | :--- | :--- |
| ... | ... | (공통 속성은 위와 동일) |
| `results.data.group`| string | 기기 (`pc`, `mo`) |
| `results.data.ratio`| number | 구간별 클릭량의 상대적 비율 |

-----

## 쇼핑인사이트 키워드 성별 트렌드 조회

### 설명

특정 쇼핑 분야와 검색 키워드의 검색 클릭 추이를 **성별**로 조회합니다.

  * **요청 URL:** `https://openapi.naver.com/v1/datalab/shopping/category/keyword/gender`
  * **프로토콜:** `HTTPS`
  * **HTTP 메서드:** `POST`

### 파라미터

| 파라미터 | 타입 | 필수 여부 | 설명 |
| :--- | :--- | :--- | :--- |
| `startDate` | string | Y | 조회 기간 시작 날짜 (yyyy-mm-dd 형식) |
| `endDate` | string | Y | 조회 기간 종료 날짜 (yyyy-mm-dd 형식) |
| `timeUnit` | string | Y | 구간 단위 (`date`, `week`, `month`) |
| `category` | string | Y | 쇼핑 분야 코드 |
| `keyword` | string | Y | 검색 키워드 |
| `device` | string | N | 기기 (`pc`, `mo`) |
| `gender` | string | N | 성별 (`m`, `f`) |
| `ages` | array(JSON)| N | 연령 (`10` \~ `60`) |

### 응답

| 속성 | 타입 | 설명 |
| :--- | :--- | :--- |
| ... | ... | (공통 속성은 위와 동일) |
| `results.data.group`| string | 성별 (`m`, `f`) |
| `results.data.ratio`| number | 구간별 클릭량의 상대적 비율 |

-----

## 쇼핑인사이트 키워드 연령별 트렌드 조회

### 설명

특정 쇼핑 분야와 검색 키워드의 검색 클릭 추이를 **연령별**로 조회합니다.

  * **요청 URL:** `https://openapi.naver.com/v1/datalab/shopping/category/keyword/age`
  * **프로토콜:** `HTTPS`
  * **HTTP 메서드:** `POST`

### 파라미터

| 파라미터 | 타입 | 필수 여부 | 설명 |
| :--- | :--- | :--- | :--- |
| `startDate` | string | Y | 조회 기간 시작 날짜 (yyyy-mm-dd 형식) |
| `endDate` | string | Y | 조회 기간 종료 날짜 (yyyy-mm-dd 형식) |
| `timeUnit` | string | Y | 구간 단위 (`date`, `week`, `month`) |
| `category` | string | Y | 쇼핑 분야 코드 |
| `keyword` | string | Y | 검색 키워드 |
| `device` | string | N | 기기 (`pc`, `mo`) |
| `gender` | string | N | 성별 (`m`, `f`) |
| `ages` | array(JSON)| N | 연령 (`10` \~ `60`) |

### 응답

| 속성 | 타입 | 설명 |
| :--- | :--- | :--- |
| ... | ... | (공통 속성은 위와 동일) |
| `results.data.group`| string | 연령 (`10` \~ `60`) |
| `results.data.ratio`| number | 구간별 클릭량의 상대적 비율 |

-----

## 오류 코드 ⚠️

| 오류 코드 | HTTP 상태 코드 | 오류 메시지 | 설명 |
| :--- | :--- | :--- | :--- |
| 400 | 400 | 잘못된 요청 | API 요청 URL의 프로토콜, 파라미터 등에 오류가 있는지 확인합니다. |
| 500 | 500 | 서버 내부 오류 | 서버 내부에 오류가 발생했습니다. "개발자 포럼"에 오류를 신고해 주십시오. |

### 403 오류

'API 권한 없음'을 의미하며, 개발자 센터에 등록한 애플리케이션에서 API 사용 설정이 되어있지 않은 경우 발생합니다. 네이버 개발자 센터의 **Application \> 내 애플리케이션 \> API 설정** 탭에서 \*\*데이터랩 (쇼핑인사이트)\*\*가 선택되어 있는지 확인하십시오.

> **참고:** 네이버 오픈API 공통 오류 코드는 "API 공통 가이드"를 참고하십시오.

-----

## 쇼핑인사이트 API 구현 예제 💻

다음은 쇼핑인사이트 API의 구현 예제입니다.

> **참고:** 예제 코드의 `YOUR_CLIENT_ID`와 `YOUR_CLIENT_SECRET`는 발급받은 애플리케이션의 클라이언트 아이디와 시크릿 값으로 변경해야 합니다.

### Java

```java
package com.naver.developers.refactoring.datalabtrend;
import java.io.*;
import java.net.HttpURLConnection;
import java.net.MalformedURLException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

public class ApiExamDatalabTrendShopping {

    public static void main(String[] args) {
        String clientId = "YOUR_CLIENT_ID"; // 애플리케이션 클라이언트 아이디
        String clientSecret = "YOUR_CLIENT_SECRET"; // 애플리케이션 클라이언트 시크릿

        String apiUrl = "https://openapi.naver.com/v1/datalab/shopping/categories";

        Map<String, String> requestHeaders = new HashMap<>();
        requestHeaders.put("X-Naver-Client-Id", clientId);
        requestHeaders.put("X-Naver-Client-Secret", clientSecret);
        requestHeaders.put("Content-Type", "application/json");

        String requestBody = "{\"startDate\":\"2017-08-01\"," +
                "\"endDate\":\"2017-09-30\"," +
                "\"timeUnit\":\"month\"," +
                "\"category\":[{\"name\":\"패션의류\",\"param\":[\"50000000\"]}," +
                              "{\"name\":\"화장품/미용\",\"param\":[\"50000002\"]}]," +
                "\"device\":\"pc\"," +
                "\"ages\":[\"20\",\"30\"]," +
                "\"gender\":\"f\"}";

        String responseBody = post(apiUrl, requestHeaders, requestBody);
        System.out.println(responseBody);
    }
    // ... (이하 post, connect, readBody 메서드 생략)
}
```

### PHP

```php
<?php
$client_id = "YOUR_CLIENT_ID";
$client_secret = "YOUR_CLIENT_SECRET";

$url = "https://openapi.naver.com/v1/datalab/shopping/categories";
$body = "{\"startDate\":\"2017-08-01\",\"endDate\":\"2017-09-30\",\"timeUnit\":\"month\",\"category\":[{\"name\":\"패션의류\",\"param\":[\"50000000\"]},{\"name\":\"화장품/미용\",\"param\":[\"50000002\"]}],\"device\":\"pc\",\"ages\":[\"20\",\"30\"],\"gender\":\"f\"}";

$ch = curl_init();
curl_setopt($ch, CURLOPT_URL, $url);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
$headers = array();
$headers[] = "X-Naver-Client-Id: ".$client_id;
$headers[] = "X-Naver-Client-Secret: ".$client_secret;
$headers[] = "Content-Type: application/json";
curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, 0);
curl_setopt($ch, CURLOPT_POSTFIELDS, $body);

$response = curl_exec ($ch);
$status_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close ($ch);

if($status_code == 200) {
    echo $response;
} else {
    echo "Error 내용:".$response;
}
?>
```

### Node.js

```javascript
var request = require('request');
var client_id = 'YOUR_CLIENT_ID';
var client_secret = 'YOUR_CLIENT_SECRET';
var api_url = 'https://openapi.naver.com/v1/datalab/shopping/categories';

var request_body = {
    "startDate": "2017-08-01",
    "endDate": "2017-09-30",
    "timeUnit": "month",
    "category": [
        {"name": "패션의류", "param": ["50000000"]},
        {"name": "화장품/미용", "param": ["50000002"]}
    ],
    "device": "pc",
    "ages": ["20", "30"],
    "gender": "f"
};

request.post({
    url: api_url,
    body: JSON.stringify(request_body),
    headers: {
        'X-Naver-Client-Id': client_id,
        'X-Naver-Client-Secret': client_secret,
        'Content-Type': 'application/json'
    }
}, function (error, response, body) {
    console.log(response.statusCode);
    console.log(body);
});
```

### Python

```python
# -*- coding: utf-8 -*-
import os
import sys
import urllib.request

client_id = "YOUR_CLIENT_ID"
client_secret = "YOUR_CLIENT_SECRET"
url = "https://openapi.naver.com/v1/datalab/shopping/categories"
body = "{\"startDate\":\"2017-08-01\",\"endDate\":\"2017-09-30\",\"timeUnit\":\"month\",\"category\":[{\"name\":\"패션의류\",\"param\":[\"50000000\"]},{\"name\":\"화장품/미용\",\"param\":[\"50000002\"]}],\"device\":\"pc\",\"ages\":[\"20\",\"30\"],\"gender\":\"f\"}"

request = urllib.request.Request(url)
request.add_header("X-Naver-Client-Id", client_id)
request.add_header("X-Naver-Client-Secret", client_secret)
request.add_header("Content-Type", "application/json")
response = urllib.request.urlopen(request, data=body.encode("utf-8"))
rescode = response.getcode()

if(rescode==200):
    response_body = response.read()
    print(response_body.decode('utf-8'))
else:
    print("Error Code:" + rescode)
```

### C\#

```csharp
using System;
using System.Net;
using System.Text;
using System.IO;

namespace NaverAPI_Guide
{
    public class APIExamDatalabTrend
    {
        static void Main(string[] args)
        {
            string url = "https://openapi.naver.com/v1/datalab/shopping/categories";
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(url);
            request.Headers.Add("X-Naver-Client-Id", "YOUR-CLIENT-ID");
            request.Headers.Add("X-Naver-Client-Secret", "YOUR-CLIENT-SECRET");
            request.ContentType = "application/json";
            request.Method = "POST";
            string body = "{\"startDate\":\"2017-08-01\",\"endDate\":\"2017-09-30\",\"timeUnit\":\"month\",\"category\":[{\"name\":\"패션의류\",\"param\":[\"50000000\"]},{\"name\":\"화장품/미용\",\"param\":[\"50000002\"]}],\"device\":\"pc\",\"ages\":[\"20\",\"30\"],\"gender\":\"f\"}";
            byte[] byteDataParams = Encoding.UTF8.GetBytes(body);
            request.ContentLength = byteDataParams.Length;
            Stream st = request.GetRequestStream();
            st.Write(byteDataParams, 0, byteDataParams.Length);
            st.Close();
            HttpWebResponse response = (HttpWebResponse)request.GetResponse();
            Stream stream = response.GetResponseStream();
            StreamReader reader = new StreamReader(stream, Encoding.UTF8);
            string text = reader.ReadToEnd();
            stream.Close();
            response.Close();
            reader.Close();
            Console.WriteLine(text);
        }
    }
}
```