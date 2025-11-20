"""BackcastPro クラスの実装

セッション間で状態を永続化する機能を提供します。
"""
from typing import Any, Dict, Union


class BackcastPro:
    """セッション間で状態を永続化するクラス
    
    このクラスのインスタンスは、実行間で状態を保持します。
    set_text(), get_text(), set_number(), get_number() メソッドを使用して
    値を保存・取得できます。
    """
    
    def __init__(self) -> None:
        """BackcastPro インスタンスを初期化"""
        self._store: Dict[str, Any] = {}
    
    def set_text(self, key: str, value: str) -> None:
        """テキスト値を保存
        
        Args:
            key: 保存するキー
            value: 保存する文字列値
        """
        self._store[key] = value
    
    def get_text(self, key: str, default: str = "") -> str:
        """テキスト値を取得
        
        Args:
            key: 取得するキー
            default: キーが存在しない場合のデフォルト値
            
        Returns:
            保存されている文字列値、またはデフォルト値
        """
        return self._store.get(key, default)
    
    def set_number(self, key: str, value: Union[int, float]) -> None:
        """数値を保存
        
        Args:
            key: 保存するキー
            value: 保存する数値（int または float）
        """
        self._store[key] = value
    
    def get_number(self, key: str, default: Union[int, float] = 0) -> Union[int, float]:
        """数値を取得
        
        Args:
            key: 取得するキー
            default: キーが存在しない場合のデフォルト値
            
        Returns:
            保存されている数値、またはデフォルト値
        """
        return self._store.get(key, default)
    
    def clear(self) -> None:
        """すべての保存された値をクリア"""
        self._store.clear()

