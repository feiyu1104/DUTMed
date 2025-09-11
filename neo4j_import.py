#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from dotenv import load_dotenv
from py2neo import Graph, Node, Relationship
import os

# 配置Neo4j连接
load_dotenv()
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
if not NEO4J_PASSWORD:
    raise EnvironmentError("请设置 NEO4J_PASSWORD 环境变量（参考 .env.example）")

# 连接Neo4j
graph = Graph(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# 读取JSON数据
with open("症状.json", "r", encoding="utf-8") as f:
    data = [json.loads(line) for line in f if line.strip()]


def merge_node(label, name, **properties):
    node = Node(label, name=name, **properties)
    graph.merge(node, label, "name")
    return node


def create_relation(start_node, rel_type, end_node):
    rel = Relationship(start_node, rel_type, end_node)
    graph.merge(rel)


for item in data:
    # 疾病节点
    disease_name = item.get("name")
    disease_props = {
        "desc": item.get("desc", ""),
        "prevent": item.get("prevent", ""),
        "cause": item.get("cause", ""),
        "get_prob": item.get("get_prob", ""),
        "easy_get": item.get("easy_get", ""),
        "get_way": item.get("get_way", ""),
        "cure_lasttime": item.get("cure_lasttime", ""),
        "cured_prob": item.get("cured_prob", ""),
        "cost_money": item.get("cost_money", ""),
        "yibao_status": item.get("yibao_status", "")
    }
    disease_node = merge_node("Disease", disease_name, **disease_props)

    # 分类节点
    for cat in item.get("category", []):
        cat_node = merge_node("Category", cat)
        create_relation(disease_node, "BELONGS_TO", cat_node)

    # 症状节点
    for sym in item.get("symptom", []):
        sym_node = merge_node("Symptom", sym)
        create_relation(disease_node, "HAS_SYMPTOM", sym_node)

    # 并发症
    for acomp in item.get("acompany", []):
        acomp_node = merge_node("Disease", acomp)
        create_relation(disease_node, "ACCOMPANIES", acomp_node)

    # 科室
    for dept in item.get("cure_department", []):
        dept_node = merge_node("Department", dept)
        create_relation(disease_node, "TREATED_BY", dept_node)

    # 治疗方法
    for treat in item.get("cure_way", []):
        treat_node = merge_node("Treatment", treat)
        create_relation(disease_node, "USES_TREATMENT", treat_node)

    # 检查项目
    for check in item.get("check", []):
        check_node = merge_node("Check", check)
        create_relation(disease_node, "REQUIRES_CHECK", check_node)

    # 推荐药物
    for drug in item.get("recommand_drug", []):
        drug_node = merge_node("Drug", drug)
        create_relation(disease_node, "RECOMMENDS_DRUG", drug_node)

    # 常用药物
    for drug in item.get("common_drug", []):
        drug_node = merge_node("Drug", drug)
        create_relation(disease_node, "COMMONLY_USES_DRUG", drug_node)

    # 宜吃食物
    for food in item.get("do_eat", []):
        food_node = merge_node("Food", food)
        create_relation(disease_node, "SHOULD_EAT", food_node)

    # 不宜吃食物
    for food in item.get("not_eat", []):
        food_node = merge_node("Food", food)
        create_relation(disease_node, "SHOULD_NOT_EAT", food_node)

    # 推荐食谱
    for recipe in item.get("recommand_eat", []):
        recipe_node = merge_node("Recipe", recipe)
        create_relation(disease_node, "RECOMMENDS_RECIPE", recipe_node)

print("导入完成！")
